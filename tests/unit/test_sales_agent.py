import json
import logging

import pytest

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import LLMError
from app.domain.models import LLMResponse
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.tools.base import ToolRegistry
from app.domain.tools.search_products import SearchProductsTool
from tests.fakes import FakeLLM, InMemoryProducts, make_product, tool_call

PRODUCTS = InMemoryProducts([make_product("black-clutch")])


def final(message: str, handles: list[str]) -> LLMResponse:
    return LLMResponse(json.dumps({"message": message, "product_handles": handles}))


def build_agent(llm: FakeLLM, max_rounds: int = 3) -> SalesAgent:
    tool = SearchProductsTool(KeywordSearch(PRODUCTS), "EGP", result_limit=5)
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
