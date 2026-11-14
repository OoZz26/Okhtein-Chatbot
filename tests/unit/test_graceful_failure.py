"""When the assistant cannot answer, the customer still gets a warm message and the chat is flagged."""

import json

import pytest

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import AllProvidersFailedError, PermanentLLMError
from app.domain.llm.fallback_chain import FallbackLLMProvider, ProviderSlot
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from app.services.chat_service import FOLLOW_UP_REASON, HOLDING_MESSAGE, ChatService
from app.services.incoming_message_service import IncomingMessageService
from tests.fakes import (
    FakeGateway,
    InMemoryFollowUps,
    InMemoryIdempotency,
    InMemoryProducts,
    ScriptedProvider,
    make_chat_service,
    make_product,
)

CHAT = "201001234567@c.us"
GOOD = LLMResponse(json.dumps({"message": "Hello!", "product_handles": [], "stage": "greet"}))


def service_over(
    primary: ScriptedProvider, fallback: ScriptedProvider | None = None
) -> tuple[ChatService, InMemoryFollowUps]:
    slots = [ProviderSlot("openai", primary)] + ([ProviderSlot("openrouter", fallback)] if fallback else [])

    async def no_sleep(_: float) -> None: ...

    llm = FallbackLLMProvider(slots, max_retries=0, base_delay_seconds=0, sleep=no_sleep)
    products = InMemoryProducts([make_product("black-clutch")])
    agent = SalesAgent(llm, ToolRegistry([]), products, load_system_prompt(), max_tool_rounds=3)
    follow_ups = InMemoryFollowUps()
    return make_chat_service(agent, follow_ups=follow_ups), follow_ups


async def test_primary_down_the_customer_still_gets_a_real_answer_from_the_fallback() -> None:
    chat, follow_ups = service_over(ScriptedProvider(PermanentLLMError("bad key")), ScriptedProvider(GOOD))

    result = await chat.handle_message(CHAT, "hi")

    assert result.reply == "Hello!"
    assert not result.degraded
    assert follow_ups.flagged == []


async def test_all_providers_failing_gives_a_warm_holding_message_and_flags_the_chat() -> None:
    chat, follow_ups = service_over(
        ScriptedProvider(PermanentLLMError("bad key")), ScriptedProvider(PermanentLLMError("no credit"))
    )

    result = await chat.handle_message(CHAT, "hi")

    assert result.degraded
    assert result.reply == HOLDING_MESSAGE
    assert "🤍" in result.reply
    assert "Traceback" not in result.reply
    assert "bad key" not in result.reply  # no internals leak to the customer
    assert follow_ups.flagged == [(CHAT, FOLLOW_UP_REASON)]


async def test_a_model_that_returns_garbage_is_handled_the_same_way() -> None:
    chat, follow_ups = service_over(ScriptedProvider(LLMResponse("this is not json")))

    result = await chat.handle_message(CHAT, "hi")

    assert result.degraded
    assert follow_ups.flagged == [(CHAT, FOLLOW_UP_REASON)]


async def test_the_incident_is_logged_with_a_masked_chat_id(caplog: pytest.LogCaptureFixture) -> None:
    chat, _ = service_over(ScriptedProvider(PermanentLLMError("bad key")))

    with caplog.at_level("ERROR"):
        await chat.handle_message(CHAT, "hi")

    assert "outcome=degraded" in caplog.text
    assert "201001234567" not in caplog.text
    assert "…4567" in caplog.text


async def test_over_whatsapp_the_holding_message_is_what_gets_sent() -> None:
    chat, _ = service_over(ScriptedProvider(AllProvidersFailedError(["x"])))
    gateway = FakeGateway()
    incoming = IncomingMessageService(chat, gateway, InMemoryIdempotency())

    from app.domain.models import IncomingMessage

    await incoming.handle(IncomingMessage("m1", CHAT, "hi"))

    assert gateway.sent == [(CHAT, HOLDING_MESSAGE)]
