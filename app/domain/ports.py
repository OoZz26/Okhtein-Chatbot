"""Ports: the interfaces the domain needs from the outside world. Adapters in `infra` implement them."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from app.domain.discovery import CustomerProfile, SessionState
from app.domain.handoff import HandoffState
from app.domain.long_term_profile import LongTermProfile
from app.domain.models import (
    ChatMessage,
    IndexedProduct,
    LLMResponse,
    Product,
    ScoredHandle,
    ToolSpec,
    VectorFilters,
)


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

    async def send_image(self, chat_id: str, image_url: str, caption: str) -> None: ...

    async def start_typing(self, chat_id: str) -> None: ...

    async def stop_typing(self, chat_id: str) -> None: ...


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

    async def messages_after(self, chat_id: str, after: datetime | None, limit: int) -> list[ChatMessage]: ...


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


class StoreInfoSource(Protocol):
    """Where the store's own facts (returns policy, brand story, ...) come from."""

    def get_knowledge(self) -> str: ...


class MessageBuffer(Protocol):
    """Collects a customer's burst of messages until they stop typing."""

    async def push(self, chat_id: str, text: str) -> int:
        """Store the message and return its sequence number (a newer push has a higher one)."""
        ...

    async def latest_sequence(self, chat_id: str) -> int: ...

    async def drain(self, chat_id: str) -> list[str]:
        """Atomically return and clear everything buffered, oldest first."""
        ...


class ChatLock(Protocol):
    """A per-chat mutex so two replies are never generated for the same chat at once."""

    async def acquire(self, chat_id: str) -> str | None:
        """Return a token if the lock was taken, None if someone else holds it."""
        ...

    async def release(self, chat_id: str, token: str) -> None:
        """Release only if `token` still owns the lock (it may have expired and been re-taken)."""
        ...


class RateLimiter(Protocol):
    """Caps how many messages we send per minute (an unofficial gateway punishes spammy accounts)."""

    async def seconds_until_allowed(self) -> float:
        """Take one slot and return 0.0, or return how long to wait when the limit is reached."""
        ...


class HandoffStore(Protocol):
    """Source of truth for whether a person has taken over a chat."""

    async def get(self, chat_id: str) -> HandoffState: ...

    async def save(self, chat_id: str, state: HandoffState) -> None: ...


class StaffNotifier(Protocol):
    """Tells the team that a customer needs a person."""

    async def notify(self, chat_id: str, state: HandoffState) -> None: ...


class Embedder(Protocol):
    """Turns text into vectors that are close together when the meanings are close."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class VectorIndex(Protocol):
    """Stores product vectors and finds the nearest ones, with filters applied in the same step."""

    async def upsert(self, items: Sequence[IndexedProduct]) -> None: ...

    async def search(self, vector: Sequence[float], filters: VectorFilters, k: int) -> list[ScoredHandle]: ...

    async def indexed_hashes(self) -> dict[str, tuple[str, str]]:
        """handle -> (content_hash, embedding_model) for everything currently indexed."""
        ...

    async def delete(self, handles: Sequence[str]) -> None: ...


class LongTermProfileStore(Protocol):
    """What we remember about a customer across visits (Postgres)."""

    async def get(self, chat_id: str) -> LongTermProfile: ...

    async def save(self, chat_id: str, profile: LongTermProfile) -> None: ...


class ProfileSummarizer(Protocol):
    """Writes a short summary of a finished session (an LLM call)."""

    async def summarize(self, messages: Sequence[ChatMessage], known: CustomerProfile) -> str: ...
