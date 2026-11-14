import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhook import get_hmac_key, get_incoming_message_service
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from app.main import create_app
from app.services.incoming_message_service import IncomingMessageService
from tests.fakes import (
    FakeGateway,
    FakeLLM,
    InMemoryIdempotency,
    InMemoryProducts,
    make_chat_service,
    make_product,
)

KEY = "test-hmac-key"
REPLY = LLMResponse(json.dumps({"message": "Hello!", "product_handles": ["black-clutch"]}))
WEBHOOK_BODY = {
    "event": "message",
    "session": "default",
    "payload": {"id": "msg-1", "from": "201001234567@c.us", "fromMe": False, "body": "hi", "hasMedia": False},
}


class SlowLLM(FakeLLM):
    async def chat(self, messages: Any, tools: Any = (), response_schema: Any = None) -> LLMResponse:
        await asyncio.sleep(0.6)
        return await super().chat(messages, tools, response_schema)


def sign(body: bytes, key: str = KEY) -> dict[str, str]:
    return {"X-Webhook-Hmac": hmac.new(key.encode(), body, hashlib.sha512).hexdigest()}


def wired_app(llm: FakeLLM) -> tuple[FastAPI, FakeGateway]:
    products = InMemoryProducts([make_product("black-clutch")])
    agent = SalesAgent(llm, ToolRegistry([]), products, load_system_prompt(), 3)
    gateway = FakeGateway()
    service = IncomingMessageService(make_chat_service(agent), gateway, InMemoryIdempotency())
    app = create_app()
    app.dependency_overrides[get_incoming_message_service] = lambda: service
    app.dependency_overrides[get_hmac_key] = lambda: KEY
    return app, gateway


@pytest.fixture
def wired() -> tuple[TestClient, FakeGateway]:
    app, gateway = wired_app(FakeLLM([REPLY] * 5))
    return TestClient(app), gateway


def post(client: TestClient, body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    raw = json.dumps(body).encode()
    return client.post("/webhook", content=raw, headers=headers if headers is not None else sign(raw))


def test_valid_webhook_gets_one_reply(wired: tuple[TestClient, FakeGateway]) -> None:
    client, gateway = wired
    assert post(client, WEBHOOK_BODY).json() == {"status": "accepted"}
    assert [chat for chat, _ in gateway.sent] == ["201001234567@c.us"]


def test_same_event_delivered_twice_gets_one_reply(wired: tuple[TestClient, FakeGateway]) -> None:
    client, gateway = wired
    post(client, WEBHOOK_BODY)
    post(client, WEBHOOK_BODY)
    assert len(gateway.sent) == 1


@pytest.mark.parametrize("headers", [{}, {"X-Webhook-Hmac": "deadbeef"}, sign(b"{}", key="wrong")])
def test_unauthenticated_calls_are_rejected(
    wired: tuple[TestClient, FakeGateway], headers: dict[str, str]
) -> None:
    client, gateway = wired
    assert post(client, WEBHOOK_BODY, headers).status_code == 401
    assert gateway.sent == []


def test_missing_server_key_rejects_everything() -> None:
    app, gateway = wired_app(FakeLLM([REPLY]))
    app.dependency_overrides[get_hmac_key] = lambda: ""
    assert post(TestClient(app), WEBHOOK_BODY, {"X-Webhook-Hmac": "x"}).status_code == 401
    assert gateway.sent == []


def test_other_events_are_acknowledged_and_ignored(wired: tuple[TestClient, FakeGateway]) -> None:
    client, gateway = wired
    assert post(client, {"event": "session.status", "payload": {}}).json() == {"status": "ignored"}
    assert gateway.sent == []


async def test_webhook_answers_fast_even_when_the_llm_is_slow() -> None:
    app, gateway = wired_app(SlowLLM([REPLY]))
    raw = json.dumps(WEBHOOK_BODY).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"x-webhook-hmac", sign(raw)["X-Webhook-Hmac"].encode()),
    ]
    scope = {
        "type": "http", "method": "POST", "path": "/webhook", "raw_path": b"/webhook", "query_string": b"",
        "headers": headers, "http_version": "1.1", "scheme": "http", "server": ("test", 80),
        "client": ("test", 1), "root_path": "",
    }  # fmt: skip
    started = time.perf_counter()
    responded_at: list[float] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(event: dict[str, Any]) -> None:
        if event["type"] == "http.response.body" and not event.get("more_body"):
            responded_at.append(time.perf_counter() - started)

    await app(scope, receive, send)  # type: ignore[arg-type]
    total = time.perf_counter() - started

    assert responded_at[0] < 0.2
    assert total > 0.5  # the slow LLM really did run, after the response had gone out
    assert len(gateway.sent) == 1
