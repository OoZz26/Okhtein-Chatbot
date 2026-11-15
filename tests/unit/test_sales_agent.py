import json
import logging

import pytest

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import LLMError
from app.domain.models import AgentContext, LLMResponse
from app.domain.tools.base import ToolRegistry
from tests.fakes import FakeLLM, InMemoryProducts, make_product, make_search_tool, tool_call

PRODUCTS = InMemoryProducts([make_product("black-clutch")])


def final(message: str, handles: list[str]) -> LLMResponse:
    return LLMResponse(json.dumps({"message": message, "product_handles": handles}))


def build_agent(llm: FakeLLM, max_rounds: int = 3) -> SalesAgent:
    tool = make_search_tool(PRODUCTS)
    return SalesAgent(llm, ToolRegistry([tool]), PRODUCTS, load_system_prompt(), max_rounds)


async def test_tool_call_result_final_answer() -> None:
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=(tool_call({"query": "black clutch"}),)),
            final("This one is perfect ✨", ["black-clutch"]),
        ]
    )
    reply = await build_agent(llm).respond("I want a black clutch")

    assert reply.message == "This one is perfect ✨"
    assert reply.product_handles == ["black-clutch"]
    tool_message = llm.calls[1][-1]
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == "call_1"
    assert "black-clutch" in tool_message.content
    assert "http" not in tool_message.content  # the model never sees URLs


async def test_unknown_handle_is_dropped_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLLM([final("Try these", ["black-clutch", "invented-bag"])])
    with caplog.at_level(logging.WARNING):
        reply = await build_agent(llm).respond("hi")

    assert reply.product_handles == ["black-clutch"]
    assert "invented-bag" in caplog.text


async def test_urls_written_by_the_model_are_removed_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLLM([final("Here https://evil.example/products/x enjoy", [])])
    with caplog.at_level(logging.WARNING):
        reply = await build_agent(llm).respond("hi")

    assert "http" not in reply.message
    assert "Removed URL" in caplog.text


async def test_tool_loop_stops_at_the_round_limit() -> None:
    looping = LLMResponse(tool_calls=(tool_call({"query": "x"}),))
    llm = FakeLLM([looping, looping, final("Sorry, nothing found", [])])
    reply = await build_agent(llm, max_rounds=2).respond("hi")

    assert reply.message == "Sorry, nothing found"
    assert len(llm.calls) == 3


async def test_unknown_tool_is_reported_back_to_the_model() -> None:
    from app.domain.models import ToolCall

    llm = FakeLLM([LLMResponse(tool_calls=(ToolCall("c1", "delete_everything", {}),)), final("ok", [])])
    await build_agent(llm).respond("hi")

    assert "unknown tool" in llm.calls[1][-1].content


async def test_non_json_reply_raises_llm_error() -> None:
    llm = FakeLLM([LLMResponse("just text")])
    with pytest.raises(LLMError):
        await build_agent(llm).respond("hi")


async def test_all_searches_of_one_round_are_answered_in_order() -> None:
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=(tool_call({"query": "a"}, "c1"), tool_call({"query": "b"}, "c2"))),
            final("ok", []),
        ]
    )
    await build_agent(llm).respond("hi")

    tool_messages = [m for m in llm.calls[1] if m.role == "tool"]
    assert [m.tool_call_id for m in tool_messages] == ["c1", "c2"]


async def test_products_already_shown_are_flagged_and_named_in_the_session_notes() -> None:
    llm = FakeLLM([LLMResponse(tool_calls=(tool_call({"query": "black clutch"}),)), final("ok", [])])
    context = AgentContext(shown_products=("black-clutch",))

    await build_agent(llm).respond("show me more", context=context)

    system = llm.calls[0][0].content
    assert "Products already shown in this chat: Black Clutch" in system
    result = json.loads(llm.calls[1][-1].content)
    assert result["results"][0]["already_shown"] is True


async def test_nothing_is_flagged_when_nothing_was_shown() -> None:
    llm = FakeLLM([LLMResponse(tool_calls=(tool_call({"query": "black clutch"}),)), final("ok", [])])

    await build_agent(llm).respond("a black clutch")

    assert "already_shown" not in llm.calls[1][-1].content
    assert "Products already shown in this chat" not in llm.calls[0][0].content


async def test_the_rule_for_this_reply_comes_right_after_the_customer_message() -> None:
    llm = FakeLLM([final("Who is it for?", [])])

    await build_agent(llm).respond("a gift", context=AgentContext(guidance="Ask about the occasion."))

    *_, user, rule = llm.calls[0]
    assert (user.role, user.content) == ("user", "a gift")
    assert (rule.role, rule.content) == ("system", "Rule for this reply: Ask about the occasion.")
    assert "Ask about the occasion." not in llm.calls[0][0].content  # not also buried in the prompt


async def test_no_rule_message_when_there_is_no_rule() -> None:
    llm = FakeLLM([final("Hi", [])])

    await build_agent(llm).respond("hi")

    assert llm.calls[0][-1].role == "user"


async def test_the_catalog_overview_reaches_the_system_prompt() -> None:
    llm = FakeLLM([final("Hi", [])])
    tool = make_search_tool(PRODUCTS)
    agent = SalesAgent(
        llm,
        ToolRegistry([tool]),
        PRODUCTS,
        load_system_prompt(),
        3,
        catalog_overview="- Wallet: sold out right now",
    )

    await agent.respond("hi")

    system = llm.calls[0][0].content
    assert "# Catalog at a glance" in system
    assert "- Wallet: sold out right now" in system


async def test_no_catalog_section_without_an_overview() -> None:
    llm = FakeLLM([final("Hi", [])])

    await build_agent(llm).respond("hi")

    assert "Catalog at a glance" not in llm.calls[0][0].content
