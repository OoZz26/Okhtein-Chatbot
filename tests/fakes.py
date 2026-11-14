"""Fakes of the domain ports, used instead of mocks so tests exercise real code paths."""

from collections.abc import Sequence
from typing import Any

from app.domain.models import ChatMessage, LLMResponse, Product, ToolCall, ToolSpec


class FakeLLM:
    """Replays scripted responses in order and records what it was asked."""

    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        return self._responses.pop(0)


class InMemoryProducts:
    def __init__(self, products: Sequence[Product]) -> None:
        self._products = list(products)

    def get(self, handle: str) -> Product | None:
        return next((p for p in self._products if p.handle == handle), None)

    def all(self) -> Sequence[Product]:
        return self._products


def make_product(handle: str = "black-clutch", **overrides: Any) -> Product:
    fields: dict[str, Any] = {
        "handle": handle,
        "title": "Black Clutch",
        "category": "Clutch",
        "color": "Black",
        "price_min": 40000.0,
        "price_max": 40000.0,
        "available": True,
    }
    fields.update(overrides)
    return Product(**fields)


def tool_call(arguments: dict[str, Any], call_id: str = "call_1") -> ToolCall:
    return ToolCall(call_id, "search_products", arguments)
