import json
from dataclasses import dataclass

import pytest

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.models import IncomingMessage, LLMResponse
from app.domain.tools.base import ToolRegistry
from app.services.debouncer import Debouncer
from app.services.incoming_message_service import TEXT_ONLY_REPLY, IncomingMessageService
from tests.fakes import (
    FakeGateway,
    FakeLLM,
    InMemoryProducts,
    make_chat_service,
    make_incoming,
    make_product,
)

CUSTOMER = "201001234567@c.us"
CLUTCH = make_product("black-clutch")


def message(**overrides: object) -> IncomingMessage:
    fields: dict[str, object] = {"message_id": "m1", "chat_id": CUSTOMER, "text": "hi"}
    fields.update(overrides)
    return IncomingMessage(**fields)  # type: ignore[arg-type]


@dataclass
class Rig:
    incoming: IncomingMessageService
    debouncer: Debouncer
    gateway: FakeGateway

    async def deliver(self, *messages: IncomingMessage) -> None:
        for item in messages:
            await self.incoming.handle(item)
        await self.debouncer.wait_idle()


def build(allowed: frozenset[str] = frozenset()) -> Rig:
    products = InMemoryProducts([CLUTCH])
    reply = LLMResponse(json.dumps({"message": "Hello!", "product_handles": ["black-clutch"]}))
    agent = SalesAgent(FakeLLM([reply] * 5), ToolRegistry([]), products, load_system_prompt(), 3)
    incoming, debouncer, gateway = make_incoming(make_chat_service(agent), allowed=allowed, products=[CLUTCH])
    return Rig(incoming, debouncer, gateway)


async def test_customer_message_gets_a_reply_in_the_same_chat() -> None:
    rig = build()
    await rig.deliver(message())

    assert rig.gateway.seen == [CUSTOMER]
    assert rig.gateway.sent == [(CUSTOMER, "Hello!")]
    assert [image[0] for image in rig.gateway.images] == [CUSTOMER]  # the product arrives as a card


async def test_duplicate_delivery_gets_exactly_one_reply() -> None:
    rig = build()
    await rig.deliver(message(), message())

    assert len(rig.gateway.sent) == 1


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
    rig = build()
    await rig.deliver(message(**overrides))

    assert rig.gateway.sent == []
    assert rig.gateway.seen == []


async def test_media_gets_the_kind_text_only_reply() -> None:
    rig = build()
    await rig.deliver(message(text="", has_media=True))

    assert rig.gateway.sent == [(CUSTOMER, TEXT_ONLY_REPLY)]


async def test_only_allowed_numbers_get_replies() -> None:
    rig = build(allowed=frozenset({"201001234567"}))
    await rig.deliver(message(message_id="a"), message(message_id="b", chat_id="209999999999@c.us"))

    assert [chat for chat, _ in rig.gateway.sent] == [CUSTOMER]
