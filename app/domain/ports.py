"""Ports: the interfaces the domain needs from the outside world. Adapters in `infra` implement them."""

from collections.abc import Sequence
from typing import Any, Protocol

from app.domain.models import ChatMessage, LLMResponse, Product, ToolSpec


class ProductRepository(Protocol):
    """Read-only access to the product catalog."""

    def get(self, handle: str) -> Product | None: ...

    def all(self) -> Sequence[Product]: ...


class LLMProvider(Protocol):
    """A chat-completion model. `response_schema`, when given, constrains the final answer to JSON."""

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse: ...
