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
