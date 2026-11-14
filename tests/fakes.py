"""Fakes of the domain ports, used instead of mocks so tests exercise real code paths."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fakeredis import FakeAsyncRedis

from app.domain.agent.sales_agent import SalesAgent
from app.domain.discovery import DiscoveryPolicy, SessionState
from app.domain.models import ChatMessage, LLMResponse, Product, ToolCall, ToolSpec
from app.infra.cache.redis_short_term import RedisShortTermMemory
from app.services.chat_service import ChatService
from app.services.memory_service import MemoryService


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


class FakeGateway:
    """Records what would have been sent to WhatsApp."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.seen: list[str] = []

    async def send_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    async def mark_seen(self, chat_id: str) -> None:
        self.seen.append(chat_id)


class InMemoryIdempotency:
    def __init__(self) -> None:
        self._claimed: set[str] = set()

    async def claim(self, key: str) -> bool:
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True


class FakeClock:
    """A clock tests can move forward by hand."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class InMemoryConversationStore:
    """Stands in for Postgres: keeps rows in lists."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, ChatMessage, datetime]] = []
        self.customers: dict[str, str] = {}

    async def upsert_customer(self, chat_id: str, display_name: str, seen_at: datetime) -> None:
        if display_name or chat_id not in self.customers:
            self.customers[chat_id] = display_name

    async def save_message(self, chat_id: str, message: ChatMessage, created_at: datetime) -> None:
        self.rows.append((chat_id, message, created_at))

    async def last_message_at(self, chat_id: str) -> datetime | None:
        times = [at for cid, _, at in self.rows if cid == chat_id]
        return max(times) if times else None

    async def recent_messages(self, chat_id: str, limit: int) -> list[ChatMessage]:
        return [m for cid, m, _ in self.rows if cid == chat_id][-limit:]


@dataclass
class MemoryRig:
    """A real MemoryService wired to fakeredis + the in-memory store, with handles to poke at them."""

    service: MemoryService
    redis: FakeAsyncRedis
    store: InMemoryConversationStore
    clock: FakeClock


def make_memory(history_limit: int = 20, ttl_seconds: int = 86400) -> MemoryRig:
    redis = FakeAsyncRedis(decode_responses=True)
    store = InMemoryConversationStore()
    clock = FakeClock()
    service = MemoryService(
        RedisShortTermMemory(redis, history_limit, ttl_seconds), store, history_limit, ttl_seconds, clock
    )
    return MemoryRig(service, redis, store, clock)


class InMemorySessionStore:
    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}

    async def load(self, chat_id: str) -> SessionState:
        return self._states.get(chat_id, SessionState())

    async def save(self, chat_id: str, state: SessionState) -> None:
        self._states[chat_id] = state


class InMemoryFollowUps:
    def __init__(self) -> None:
        self.flagged: list[tuple[str, str]] = []

    async def flag(self, chat_id: str, reason: str) -> None:
        self.flagged.append((chat_id, reason))


def make_chat_service(
    agent: SalesAgent,
    rig: MemoryRig | None = None,
    sessions: InMemorySessionStore | None = None,
    max_questions: int = 3,
    store_url: str = "https://eg.okhtein.com",
    follow_ups: InMemoryFollowUps | None = None,
) -> ChatService:
    """A real ChatService wired to fakes for every port."""
    return ChatService(
        agent,
        (rig or make_memory()).service,
        sessions or InMemorySessionStore(),
        DiscoveryPolicy(max_questions),
        follow_ups or InMemoryFollowUps(),
        store_url,
    )


class ScriptedProvider:
    """An LLM provider that replays scripted outcomes: each is a response to return or an error to raise."""

    def __init__(self, *outcomes: LLMResponse | Exception) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
