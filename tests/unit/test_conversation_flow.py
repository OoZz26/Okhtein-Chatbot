"""Multi-turn behaviour of ChatService: the agent receives the earlier conversation."""

import json

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from app.services.chat_service import ChatService
from tests.fakes import (
    FakeLLM,
    InMemoryProducts,
    MemoryRig,
    make_chat_service,
    make_memory,
    make_product,
)

CHAT = "201001234567@c.us"


def reply(message: str, handles: list[str] | None = None) -> LLMResponse:
    return LLMResponse(json.dumps({"message": message, "product_handles": handles or []}))


def build(llm: FakeLLM, rig: MemoryRig) -> ChatService:
    products = InMemoryProducts([make_product("black-clutch")])
    agent = SalesAgent(llm, ToolRegistry([]), products, load_system_prompt(), max_tool_rounds=3)
    return make_chat_service(agent, rig)


async def test_second_message_sees_the_first_exchange() -> None:
    llm = FakeLLM([reply("Try the Black Clutch, 40,000 EGP", ["black-clutch"]), reply("A cheaper one...")])
    service = build(llm, make_memory())

    await service.handle_message(CHAT, "I want a clutch")
    await service.handle_message(CHAT, "show me a cheaper one")

    second_call = llm.calls[1]
    assert [m.role for m in second_call] == ["system", "user", "assistant", "user"]
    assert second_call[1].content == "I want a clutch"
    assert "Black Clutch, 40,000 EGP" in second_call[2].content
    assert "black-clutch" in second_call[2].content  # the link the customer saw is remembered too
    assert second_call[3].content == "show me a cheaper one"


async def test_context_survives_a_redis_flush() -> None:
    rig = make_memory()
    llm = FakeLLM([reply("Try the Black Clutch"), reply("Cheaper option")])
    service = build(llm, rig)

    await service.handle_message(CHAT, "I want a clutch")
    await rig.redis.flushall()
    await service.handle_message(CHAT, "cheaper?")

    assert [m.content for m in llm.calls[1][1:3]] == ["I want a clutch", "Try the Black Clutch"]


async def test_at_most_n_history_messages_reach_the_llm() -> None:
    rig = make_memory(history_limit=4)
    llm = FakeLLM([reply(f"answer {i}") for i in range(6)])
    service = build(llm, rig)

    for i in range(6):
        await service.handle_message(CHAT, f"question {i}")

    last_call = [m for m in llm.calls[-1] if m.role != "system"]  # drop the prompt and the turn's rule
    history = last_call[:-1]  # everything before the new user message
    assert len(history) == 4
    assert history[-1].content == "answer 4"


async def test_every_message_is_stored_with_chat_id_role_and_time() -> None:
    rig = make_memory()
    service = build(FakeLLM([reply("hello")]), rig)

    await service.handle_message(CHAT, "hi", sender_name="Sara")

    assert [(cid, m.role, m.content) for cid, m, _ in rig.store.rows] == [
        (CHAT, "user", "hi"),
        (CHAT, "assistant", "hello"),
    ]
    assert all(at == rig.clock.now for _, _, at in rig.store.rows)
    assert rig.store.customers[CHAT] == "Sara"


async def test_a_new_session_starts_with_no_history() -> None:
    rig = make_memory(ttl_seconds=3600)
    llm = FakeLLM([reply("first"), reply("second")])
    service = build(llm, rig)

    await service.handle_message(CHAT, "hi")
    await rig.redis.flushall()
    rig.clock.advance(hours=3)
    await service.handle_message(CHAT, "hi again")

    assert [m.role for m in llm.calls[1] if m.role != "system"] == ["user"]  # no history at all
