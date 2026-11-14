import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.chat import get_chat_service
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import LLMError
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from app.main import create_app
from app.services.chat_service import HOLDING_MESSAGE, ChatService
from tests.fakes import (
    FakeLLM,
    InMemoryProducts,
    make_chat_service,
    make_product,
    make_search_tool,
    tool_call,
)

PRODUCTS = InMemoryProducts([make_product("black-clutch")])


class FailingLLM:
    async def chat(self, *_args: object, **_kwargs: object) -> LLMResponse:
        raise LLMError("boom")


def service_with(llm: object) -> ChatService:
    tool = make_search_tool(PRODUCTS)
    agent = SalesAgent(llm, ToolRegistry([tool]), PRODUCTS, load_system_prompt(), 3)  # type: ignore[arg-type]
    return make_chat_service(agent)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        test_client.app = app  # type: ignore[attr-defined]
        yield test_client


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_returns_a_reply_with_a_real_link(client: TestClient) -> None:
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=(tool_call({"query": "black clutch"}),)),
            LLMResponse(json.dumps({"message": "Meet your clutch ✨", "product_handles": ["black-clutch"]})),
        ]
    )
    client.app.dependency_overrides[get_chat_service] = lambda: service_with(llm)  # type: ignore[attr-defined]

    response = client.post("/chat", json={"chat_id": "c1", "text": "I want a black clutch"})

    assert response.status_code == 200
    body = response.json()
    assert body["links"] == ["https://eg.okhtein.com/products/black-clutch"]
    assert body["links"][0] in body["reply"]


def test_llm_failure_gives_the_customer_a_friendly_holding_reply(client: TestClient) -> None:
    client.app.dependency_overrides[get_chat_service] = lambda: service_with(FailingLLM())  # type: ignore[attr-defined]

    response = client.post("/chat", json={"chat_id": "c1", "text": "hi"})

    assert response.status_code == 200  # the customer never sees an error
    assert response.json()["reply"] == HOLDING_MESSAGE
    assert response.json()["links"] == []


def test_empty_text_is_rejected(client: TestClient) -> None:
    # Override the service so the test never depends on real API keys being present in .env.
    client.app.dependency_overrides[get_chat_service] = lambda: service_with(FailingLLM())  # type: ignore[attr-defined]
    assert client.post("/chat", json={"chat_id": "c1", "text": ""}).status_code == 422
