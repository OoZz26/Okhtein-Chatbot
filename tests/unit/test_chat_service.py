import json

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from tests.fakes import FakeLLM, InMemoryProducts, make_chat_service, make_product


async def test_links_are_built_from_handles_not_from_the_model() -> None:
    products = InMemoryProducts([make_product("black-clutch")])
    llm = FakeLLM([LLMResponse(json.dumps({"message": "Lovely pick", "product_handles": ["black-clutch"]}))])
    agent = SalesAgent(llm, ToolRegistry([]), products, load_system_prompt(), max_tool_rounds=3)

    result = await make_chat_service(agent, store_url="https://eg.okhtein.com/").handle_message(
        "chat-1", "hi"
    )

    assert result.links == ["https://eg.okhtein.com/products/black-clutch"]
    assert result.reply == "Lovely pick\n\nhttps://eg.okhtein.com/products/black-clutch"


async def test_a_product_card_is_never_sent_twice_in_one_session() -> None:
    products = InMemoryProducts([make_product("black-clutch"), make_product("gold-ring", title="Gold Ring")])
    replies = [
        {"message": "Try this", "product_handles": ["black-clutch"]},
        {"message": "And these", "product_handles": ["black-clutch", "gold-ring"]},
        {"message": "Here it is again", "product_handles": ["black-clutch"]},
    ]
    llm = FakeLLM([LLMResponse(json.dumps(r)) for r in replies])
    agent = SalesAgent(llm, ToolRegistry([]), products, load_system_prompt(), max_tool_rounds=3)
    service = make_chat_service(agent)

    first = await service.handle_message("chat-1", "show me something")
    second = await service.handle_message("chat-1", "more please")
    third = await service.handle_message("chat-1", "the clutch again?")

    assert first.product_handles == ["black-clutch"]
    assert second.product_handles == ["gold-ring"]  # the clutch was already seen
    assert third.product_handles == ["black-clutch"]  # asked for again: only seen products, so sent
