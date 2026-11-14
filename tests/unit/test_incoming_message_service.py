import json

import pytest

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.models import IncomingMessage, LLMResponse
from app.domain.tools.base import ToolRegistry
from app.services.chat_service import ChatService
from app.services.incoming_message_service import TEXT_ONLY_REPLY, IncomingMessageService
from tests.fakes import (
    FakeGateway,
    FakeLLM,
    InMemoryIdempotency,
    InMemoryProducts,
    make_memory,
    make_product,
)

CUSTOMER = "201001234567@c.us"


def message(**overrides: object) -> IncomingMessage:
    fields: dict[str, object] = {"message_id": "m1", "chat_id": CUSTOMER, "text": "hi"}
    fields.update(overrides)
    return IncomingMessage(**fields)  # type: ignore[arg-type]


def build(
    llm_replies: int = 5, allowed: frozenset[str] = frozenset()
) -> tuple[IncomingMessageService, FakeGateway]:
    products = InMemoryProducts([make_product("black-clutch")])
    reply = LLMResponse(json.dumps({"message": "Hello!", "product_handles": ["black-clutch"]}))
    agent = SalesAgent(FakeLLM([reply] * llm_replies), ToolRegistry([]), products, load_system_prompt(), 3)
    gateway = FakeGateway()
    service = IncomingMessageService(
        ChatService(agent, make_memory().service, "https://eg.okhtein.com"),
        gateway,
        InMemoryIdempotency(),
        allowed,
    )
    return service, gateway


async def test_customer_message_gets_a_reply_in_the_same_chat() -> None:
    service, gateway = build()
    await service.handle(message())

    assert gateway.seen == [CUSTOMER]
    assert gateway.sent == [(CUSTOMER, "Hello!\n\nhttps://eg.okhtein.com/products/black-clutch")]


async def test_duplicate_delivery_gets_exactly_one_reply() -> None:
    service, gateway = build()
    await service.handle(message())
    await service.handle(message())

    assert len(gateway.sent) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"from_me": True},
        {"is_group": True, "chat_id": "1203630@g.us"},
        {"is_status": True, "chat_id": "status@broadcast"},
    ],
    ids=["own message", "group", "status broadcast"],
)
async def test_ignored_messages_produce_no_reply(overrides: dict[str, object]) -> None:
    service, gateway = build()
    await service.handle(message(**overrides))

    assert gateway.sent == []
    assert gateway.seen == []


async def test_media_gets_the_kind_text_only_reply() -> None:
    service, gateway = build()
    await service.handle(message(text="", has_media=True))

    assert gateway.sent == [(CUSTOMER, TEXT_ONLY_REPLY)]


async def test_only_allowed_numbers_get_replies() -> None:
    service, gateway = build(allowed=frozenset({"201001234567"}))
    await service.handle(message(message_id="a"))
    await service.handle(message(message_id="b", chat_id="209999999999@c.us"))

    assert [chat for chat, _ in gateway.sent] == [CUSTOMER]
