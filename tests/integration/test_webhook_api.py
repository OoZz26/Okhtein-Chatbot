import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.webhook import get_hmac_key, get_incoming_message_service
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from app.main import create_app
from app.services.debouncer import Debouncer
from tests.fakes import (
    FakeGateway,
    FakeLLM,
    InMemoryProducts,
    make_chat_service,
    make_incoming,
    make_product,
)

KEY = "test-hmac-key"
CLUTCH = make_product("black-clutch")
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


@dataclass
class Wired:
    app: FastAPI
    gateway: FakeGateway
    debouncer: Debouncer

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")


def sign(body: bytes, key: str = KEY) -> dict[str, str]:
    return {"X-Webhook-Hmac": hmac.new(key.encode(), body, hashlib.sha512).hexdigest()}


def wired_app(llm: FakeLLM) -> Wired:
    agent = SalesAgent(llm, ToolRegistry([]), InMemoryProducts([CLUTCH]), load_system_prompt(), 3)
    incoming, debouncer, gateway = make_incoming(make_chat_service(agent), products=[CLUTCH])
    app = create_app()
    app.dependency_overrides[get_incoming_message_service] = lambda: incoming
    app.dependency_overrides[get_hmac_key] = lambda: KEY
    return Wired(app, gateway, debouncer)


@pytest.fixture
def wired() -> Wired:
    return wired_app(FakeLLM([REPLY] * 5))


async def post(wired: Wired, body: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
    raw = json.dumps(body).encode()
    async with wired.client() as client:
        return await client.post(
            "/webhook", content=raw, headers=headers if headers is not None else sign(raw)
        )


async def test_valid_webhook_gets_one_reply(wired: Wired) -> None:
    response = await post(wired, WEBHOOK_BODY)
    await wired.debouncer.wait_idle()

    assert response.json() == {"status": "accepted"}
    assert [chat for chat, _ in wired.gateway.sent] == ["201001234567@c.us"]


async def test_same_event_delivered_twice_gets_one_reply(wired: Wired) -> None:
    await post(wired, WEBHOOK_BODY)
    await post(wired, WEBHOOK_BODY)
    await wired.debouncer.wait_idle()

    assert len(wired.gateway.sent) == 1


@pytest.mark.parametrize("headers", [{}, {"X-Webhook-Hmac": "deadbeef"}, sign(b"{}", key="wrong")])
async def test_unauthenticated_calls_are_rejected(wired: Wired, headers: dict[str, str]) -> None:
    response = await post(wired, WEBHOOK_BODY, headers)
    await wired.debouncer.wait_idle()

    assert response.status_code == 401
    assert wired.gateway.sent == []


async def test_missing_server_key_rejects_everything() -> None:
    wired = wired_app(FakeLLM([REPLY]))
    wired.app.dependency_overrides[get_hmac_key] = lambda: ""

    response = await post(wired, WEBHOOK_BODY, {"X-Webhook-Hmac": "x"})

    assert response.status_code == 401
    assert wired.gateway.sent == []


async def test_other_events_are_acknowledged_and_ignored(wired: Wired) -> None:
    response = await post(wired, {"event": "session.status", "payload": {}})

    assert response.json() == {"status": "ignored"}
    assert wired.gateway.sent == []


async def test_webhook_answers_fast_even_when_the_llm_is_slow() -> None:
    wired = wired_app(SlowLLM([REPLY]))
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

    await wired.app(scope, receive, send)  # type: ignore[arg-type]
    assert responded_at[0] < 0.2  # answered before the slow LLM even finished
    assert wired.gateway.sent == []  # nothing was sent yet: the reply is still being generated

    await wired.debouncer.wait_idle()
    assert time.perf_counter() - started > 0.5  # the slow LLM really did run, after the response went out
    assert len(wired.gateway.sent) == 1
