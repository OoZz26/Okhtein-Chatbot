"""Fakes of the domain ports, used instead of mocks so tests exercise real code paths."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fakeredis import FakeAsyncRedis

from app.domain.agent.sales_agent import SalesAgent
from app.domain.discovery import CustomerProfile, DiscoveryPolicy, SessionState
from app.domain.errors import LLMError, MessagingError, RetrievalError
from app.domain.handoff import HandoffState
from app.domain.long_term_profile import LongTermProfile
from app.domain.models import (
    ChatMessage,
    IndexedProduct,
    LLMResponse,
    Product,
    ScoredHandle,
    ToolCall,
    ToolSpec,
    VectorFilters,
)
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.retrieval.retrievers import KeywordRetriever
from app.domain.tools.search_products import SearchProductsTool
from app.infra.cache.redis_short_term import RedisShortTermMemory
from app.services.chat_service import ChatService
from app.services.debouncer import Debouncer
from app.services.handoff_service import HandoffService
from app.services.incoming_message_service import IncomingMessageService
from app.services.memory_service import MemoryService
from app.services.product_cards import ProductCardFactory
from app.services.reply_sender import ReplySender
from app.services.reply_service import ReplyService
from app.services.returning_customer_service import ReturningCustomerService


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
    """Records what would have been sent to WhatsApp, in order."""

    def __init__(self, fail_images: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.images: list[tuple[str, str, str]] = []
        self.seen: list[str] = []
        self.events: list[str] = []
        self.fail_images = fail_images

    async def send_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))
        self.events.append("text")

    async def mark_seen(self, chat_id: str) -> None:
        self.seen.append(chat_id)

    async def send_image(self, chat_id: str, image_url: str, caption: str) -> None:
        if self.fail_images:
            raise MessagingError("image could not be sent")
        self.images.append((chat_id, image_url, caption))
        self.events.append("image")

    async def start_typing(self, chat_id: str) -> None:
        self.events.append("typing_on")

    async def stop_typing(self, chat_id: str) -> None:
        self.events.append("typing_off")


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

    async def messages_after(self, chat_id: str, after: datetime | None, limit: int) -> list[ChatMessage]:
        rows = [m for cid, m, at in self.rows if cid == chat_id and (after is None or at > after)]
        return rows[:limit]


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
    handoffs: HandoffService | None = None,
    returning: ReturningCustomerService | None = None,
) -> ChatService:
    """A real ChatService wired to fakes for every port."""
    rig = rig or make_memory()
    return ChatService(
        agent,
        rig.service,
        sessions or InMemorySessionStore(),
        DiscoveryPolicy(max_questions),
        follow_ups or InMemoryFollowUps(),
        handoffs or make_handoffs().service,
        returning or make_returning(rig).service,
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


class InMemoryBuffer:
    def __init__(self) -> None:
        self._items: dict[str, list[str]] = {}
        self._sequence: dict[str, int] = {}

    async def push(self, chat_id: str, text: str) -> int:
        self._items.setdefault(chat_id, []).append(text)
        self._sequence[chat_id] = self._sequence.get(chat_id, 0) + 1
        return self._sequence[chat_id]

    async def latest_sequence(self, chat_id: str) -> int:
        return self._sequence.get(chat_id, 0)

    async def drain(self, chat_id: str) -> list[str]:
        return self._items.pop(chat_id, [])


class InMemoryLock:
    def __init__(self) -> None:
        self.held: dict[str, str] = {}
        self._counter = 0

    async def acquire(self, chat_id: str) -> str | None:
        if chat_id in self.held:
            return None
        self._counter += 1
        self.held[chat_id] = f"token-{self._counter}"
        return self.held[chat_id]

    async def release(self, chat_id: str, token: str) -> None:
        if self.held.get(chat_id) == token:
            del self.held[chat_id]


class NoLimit:
    async def seconds_until_allowed(self) -> float:
        return 0.0


async def instant(_: float) -> None:
    """A sleep that does not wait (and does not yield): tests stay fast and deterministic."""


async def quick_yield(_: float) -> None:
    """A sleep that only yields to other tasks: for tests where tasks must interleave for real."""
    await asyncio.sleep(0.001)


def make_incoming(
    chat_service: ChatService,
    gateway: FakeGateway | None = None,
    allowed: frozenset[str] = frozenset(),
    idempotency: InMemoryIdempotency | None = None,
    products: Sequence[Product] = (),
    handoffs: HandoffService | None = None,
) -> tuple[IncomingMessageService, Debouncer, FakeGateway]:
    """The whole inbound pipeline over fakes. Call `await debouncer.wait_idle()` to let replies finish."""
    gateway = gateway or FakeGateway()
    sender = ReplySender(
        gateway, NoLimit(), max_bubbles=3, seconds_per_char=0.0, max_typing_delay_seconds=0.0, sleep=instant
    )
    cards = ProductCardFactory(InMemoryProducts(products), "https://eg.okhtein.com", "EGP")
    replies = ReplyService(chat_service, gateway, sender, cards)
    debouncer = Debouncer(InMemoryBuffer(), InMemoryLock(), replies.reply, 0.0, 1.0, sleep=instant)
    incoming = IncomingMessageService(
        gateway, idempotency or InMemoryIdempotency(), debouncer, handoffs or make_handoffs().service, allowed
    )
    return incoming, debouncer, gateway


class InMemoryHandoffStore:
    def __init__(self) -> None:
        self.states: dict[str, HandoffState] = {}

    async def get(self, chat_id: str) -> HandoffState:
        return self.states.get(chat_id, HandoffState())

    async def save(self, chat_id: str, state: HandoffState) -> None:
        self.states[chat_id] = state


class RecordingNotifier:
    def __init__(self) -> None:
        self.notified: list[tuple[str, HandoffState]] = []

    async def notify(self, chat_id: str, state: HandoffState) -> None:
        self.notified.append((chat_id, state))


@dataclass
class HandoffRig:
    service: HandoffService
    store: InMemoryHandoffStore
    notifier: RecordingNotifier
    clock: FakeClock


def make_handoffs(timeout_hours: float = 12.0) -> HandoffRig:
    store, notifier, clock = InMemoryHandoffStore(), RecordingNotifier(), FakeClock()
    return HandoffRig(HandoffService(store, notifier, timeout_hours, clock), store, notifier, clock)


def make_search_tool(products: InMemoryProducts, limit: int = 5) -> SearchProductsTool:
    """The search tool over plain keyword retrieval: no embeddings, no database."""
    search = KeywordSearch(products)
    return SearchProductsTool(KeywordRetriever(search), search.categories(), "EGP", limit)


class FakeEmbedder:
    """Deterministic 'embeddings': hashed bag of words, so shared words mean similar vectors. No network."""

    DIMENSIONS = 64

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.embedded_texts: list[str] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise RetrievalError("embedding service is down")
        self.embedded_texts.extend(texts)
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.DIMENSIONS
        for word in text.lower().split():
            vector[sum(map(ord, word)) % self.DIMENSIONS] += 1.0
        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        return [v / norm for v in vector]


class InMemoryVectorIndex:
    """A brute-force vector index with the same filters as the pgvector one."""

    def __init__(self, fail: bool = False) -> None:
        self.items: dict[str, IndexedProduct] = {}
        self.fail = fail

    async def upsert(self, items: Sequence[IndexedProduct]) -> None:
        for item in items:
            self.items[item.handle] = item

    async def search(self, vector: Sequence[float], filters: VectorFilters, k: int) -> list[ScoredHandle]:
        if self.fail:
            raise RetrievalError("vector index is down")
        hits = [
            ScoredHandle(item.handle, sum(a * b for a, b in zip(vector, item.embedding, strict=True)))
            for item in self.items.values()
            if (item.available or not filters.in_stock_only)
            and (filters.max_price is None or item.price_min <= filters.max_price)
            and (not filters.category or filters.category.lower() in item.category.lower())
        ]
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:k]

    async def indexed_hashes(self) -> dict[str, tuple[str, str]]:
        return {h: (item.content_hash, item.embedding_model) for h, item in self.items.items()}

    async def delete(self, handles: Sequence[str]) -> None:
        for handle in handles:
            self.items.pop(handle, None)


class InMemoryProfileStore:
    def __init__(self) -> None:
        self.profiles: dict[str, LongTermProfile] = {}

    async def get(self, chat_id: str) -> LongTermProfile:
        return self.profiles.get(chat_id, LongTermProfile())

    async def save(self, chat_id: str, profile: LongTermProfile) -> None:
        self.profiles[chat_id] = profile


class FakeSummarizer:
    """Returns scripted summaries and records what it was asked to summarise."""

    def __init__(self, *summaries: str, fail: bool = False) -> None:
        self._summaries = list(summaries) or ["Likes bold gold pieces."]
        self.fail = fail
        self.calls: list[list[ChatMessage]] = []

    async def summarize(self, messages: Sequence[ChatMessage], known: CustomerProfile) -> str:
        self.calls.append(list(messages))
        if self.fail:
            raise LLMError("summarizer down")
        return self._summaries.pop(0) if len(self._summaries) > 1 else self._summaries[0]


@dataclass
class ReturningRig:
    service: ReturningCustomerService
    profiles: InMemoryProfileStore
    summarizer: FakeSummarizer


def make_returning(rig: MemoryRig | None = None, summarizer: FakeSummarizer | None = None) -> ReturningRig:
    """ReturningCustomerService over fakes, sharing the memory rig's store and clock."""
    rig = rig or make_memory()
    profiles, summarizer = InMemoryProfileStore(), summarizer or FakeSummarizer()
    service = ReturningCustomerService(
        profiles, rig.store, summarizer, summary_max_chars=300, shown_limit=20, clock=rig.clock
    )
    return ReturningRig(service, profiles, summarizer)
