import json
from typing import Any

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import PermanentLLMError
from app.domain.llm.fallback_chain import FallbackLLMProvider, ProviderSlot
from app.domain.models import IncomingMessage, LLMResponse
from app.domain.tools.base import ToolRegistry
from app.services.chat_service import HOLDING_MESSAGE, ChatResult
from app.services.product_cards import ProductCardFactory
from app.services.reply_sender import ReplySender
from app.services.reply_service import ReplyService
from tests.fakes import (
    FakeGateway,
    FakeLLM,
    InMemoryProducts,
    NoLimit,
    ScriptedProvider,
    instant,
    make_chat_service,
    make_incoming,
    make_product,
)

CHAT = "201001234567@c.us"
CLUTCH = make_product("black-clutch", image_url="https://img/black-clutch.jpg")


async def run(llm: Any) -> FakeGateway:
    agent = SalesAgent(llm, ToolRegistry([]), InMemoryProducts([CLUTCH]), load_system_prompt(), 3)
    incoming, debouncer, gateway = make_incoming(make_chat_service(agent), products=[CLUTCH])
    await incoming.handle(IncomingMessage("m1", CHAT, "I want a clutch"))
    await debouncer.wait_idle()
    return gateway


async def test_typing_is_on_while_generating_and_off_afterwards() -> None:
    reply = LLMResponse(json.dumps({"message": "Here!", "product_handles": ["black-clutch"]}))
    gateway = await run(FakeLLM([reply]))

    assert gateway.events[0] == "typing_on"
    assert gateway.events[-1] == "typing_off"
    assert gateway.events.index("text") < gateway.events.index("image")


async def test_the_card_has_the_name_the_price_and_the_real_link() -> None:
    reply = LLMResponse(json.dumps({"message": "Here!", "product_handles": ["black-clutch"]}))
    gateway = await run(FakeLLM([reply]))

    _, image_url, caption = gateway.images[0]
    assert image_url == "https://img/black-clutch.jpg"
    assert caption == "*Black Clutch*\n40,000 EGP\nhttps://eg.okhtein.com/products/black-clutch"
    assert gateway.sent == [(CHAT, "Here!")]  # the text itself carries no link: the card does


async def test_typing_is_cleared_even_when_the_assistant_fails() -> None:
    failing = FallbackLLMProvider(
        [ProviderSlot("openai", ScriptedProvider(PermanentLLMError("bad key")))], 0, 0, sleep=instant
    )
    gateway = await run(failing)

    assert gateway.events[-1] == "typing_off"
    assert len(gateway.sent) >= 1  # the holding message went out


class BrokenStorageChat:
    """A chat service whose database is down: it raises something that is not an OkhteinError."""

    async def is_handed_off(self, chat_id: str) -> bool:
        return False

    async def handle_message(self, chat_id: str, text: str, sender_name: str = "") -> ChatResult:
        raise ConnectionError("postgres is restarting")


async def test_an_unexpected_storage_failure_still_gets_the_holding_message() -> None:
    gateway = FakeGateway()
    sender = ReplySender(gateway, NoLimit(), 3, 0.0, 0.0, sleep=instant)
    cards = ProductCardFactory(InMemoryProducts([]), "https://eg.okhtein.com", "EGP")
    service = ReplyService(BrokenStorageChat(), gateway, sender, cards)  # type: ignore[arg-type]

    await service.reply(CHAT, "hi")

    assert gateway.sent == [(CHAT, HOLDING_MESSAGE)]  # never silence
    assert gateway.events[-1] == "typing_off"
