"""Ports: the interfaces the domain needs from the outside world. Adapters in `infra` implement them."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from app.domain.discovery import SessionState
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


class MessagingGateway(Protocol):
    """Sends WhatsApp messages. The services never know which gateway sits behind it."""

    async def send_text(self, chat_id: str, text: str) -> None: ...

    async def mark_seen(self, chat_id: str) -> None: ...


class IdempotencyStore(Protocol):
    """Remembers which keys were already handled."""

    async def claim(self, key: str) -> bool:
        """Return True if this is the first time `key` is seen, False if it was already claimed."""
        ...


class ShortTermMemory(Protocol):
    """Fast, expiring store for the current conversation (Redis)."""

    async def append(self, chat_id: str, message: ChatMessage) -> None: ...

    async def recent(self, chat_id: str, limit: int) -> list[ChatMessage]: ...

    async def clear(self, chat_id: str) -> None: ...


class ConversationStore(Protocol):
    """Durable source of truth for every message and customer (Postgres)."""

    async def upsert_customer(self, chat_id: str, display_name: str, seen_at: datetime) -> None: ...

    async def save_message(self, chat_id: str, message: ChatMessage, created_at: datetime) -> None: ...

    async def last_message_at(self, chat_id: str) -> datetime | None: ...

    async def recent_messages(self, chat_id: str, limit: int) -> list[ChatMessage]: ...


class ConversationMemory(Protocol):
    """What the chat service needs to remember a conversation. Storage details stay hidden."""

    async def context(self, chat_id: str) -> list[ChatMessage]: ...

    async def record(self, chat_id: str, message: ChatMessage, display_name: str = "") -> None: ...

    async def is_new_session(self, chat_id: str) -> bool: ...


class SessionStore(Protocol):
    """Remembers the discovery state (stage, customer profile, questions asked) for a chat session."""

    async def load(self, chat_id: str) -> SessionState: ...

    async def save(self, chat_id: str, state: SessionState) -> None: ...


class FollowUpStore(Protocol):
    """Flags chats where a human should follow up (for example when the assistant could not answer)."""

    async def flag(self, chat_id: str, reason: str) -> None: ...
