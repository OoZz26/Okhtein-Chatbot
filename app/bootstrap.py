"""Composition root: the ONE place where concrete classes are chosen and wired together."""

import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.catalog_overview import render_catalog_overview
from app.domain.discovery import DiscoveryPolicy
from app.domain.errors import ConfigurationError
from app.domain.llm.fallback_chain import FallbackLLMProvider, ProviderSlot
from app.domain.ports import LLMProvider, MessagingGateway, StaffNotifier
from app.domain.profile_summarizer import LLMProfileSummarizer
from app.domain.retrieval.base import Retriever
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.retrieval.retrievers import (
    FallbackRetriever,
    HybridRetriever,
    KeywordRetriever,
    VectorRetriever,
)
from app.domain.tools.base import ToolRegistry
from app.domain.tools.search_products import SearchProductsTool
from app.infra.cache.redis_buffer import RedisMessageBuffer
from app.infra.cache.redis_handoff_cache import CachedHandoffStore
from app.infra.cache.redis_idempotency import RedisIdempotencyStore
from app.infra.cache.redis_lock import RedisChatLock
from app.infra.cache.redis_rate_limiter import RedisRateLimiter
from app.infra.cache.redis_session_store import RedisSessionStore
from app.infra.cache.redis_short_term import RedisShortTermMemory
from app.infra.catalog.file_store_info import FileStoreInfoSource
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.db.conversation_store import PostgresConversationStore
from app.infra.db.follow_up_store import PostgresFollowUpStore
from app.infra.db.handoff_store import PostgresHandoffStore
from app.infra.db.pgvector_index import PgVectorIndex, ensure_vector_support
from app.infra.db.profile_store import PostgresProfileStore
from app.infra.db.session import create_engine, create_session_factory, create_tables
from app.infra.llm.openai_embedder import OpenAIEmbedder
from app.infra.llm.openai_provider import OpenAICompatibleProvider
from app.infra.loadtest.fakes import FakeLatencyLLM, RecordingGateway
from app.infra.whatsapp.staff_notifier import (
    CompositeStaffNotifier,
    LogStaffNotifier,
    WhatsAppStaffNotifier,
)
from app.infra.whatsapp.waha_gateway import WahaGateway
from app.services.chat_service import ChatService
from app.services.debouncer import Debouncer
from app.services.handoff_service import HandoffService
from app.services.incoming_message_service import IncomingMessageService
from app.services.memory_service import MemoryService
from app.services.product_cards import ProductCardFactory
from app.services.reply_sender import ReplySender
from app.services.reply_service import ReplyService
from app.services.returning_customer_service import ReturningCustomerService

logger = logging.getLogger(__name__)

LOCK_RENEWALS_PER_TTL = 3  # renew well before expiry, so one slow Redis call cannot lose the lock


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


@lru_cache
def _engine() -> AsyncEngine:
    s = get_settings()
    return create_engine(
        s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db
    )


@lru_cache
def _products() -> JsonProductRepository:
    return JsonProductRepository(Path(get_settings().products_path))


@lru_cache
def build_memory_service() -> MemoryService:
    settings = get_settings()
    return MemoryService(
        short_term=RedisShortTermMemory(_redis(), settings.history_limit, settings.session_ttl_seconds),
        store=PostgresConversationStore(create_session_factory(_engine())),
        history_limit=settings.history_limit,
        session_ttl_seconds=settings.session_ttl_seconds,
    )


def _openai(settings: Settings) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        settings.openai_api_key,
        settings.openai_model,
        settings.llm_timeout_seconds,
        reasoning_effort=settings.openai_reasoning_effort,
    )


def _openrouter(settings: Settings) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.llm_timeout_seconds,
        base_url=settings.openrouter_base_url,
        headers={"X-Title": "Okhtein WhatsApp Assistant"},
    )


def build_llm(settings: Settings) -> LLMProvider:
    """The provider chain, in the configured order. Providers without an API key are skipped."""
    if settings.load_test_mode:
        return FakeLatencyLLM()
    factories: dict[str, tuple[str, Callable[[Settings], OpenAICompatibleProvider]]] = {
        "openai": (settings.openai_api_key, _openai),
        "openrouter": (settings.openrouter_api_key, _openrouter),
    }
    slots = []
    for name in (n.strip() for n in settings.llm_provider_order.split(",") if n.strip()):
        if name not in factories:
            raise ConfigurationError(f"Unknown provider {name!r} in LLM_PROVIDER_ORDER")
        api_key, factory = factories[name]
        if api_key:
            slots.append(ProviderSlot(name, factory(settings)))
        else:
            logger.warning("LLM provider %s is in LLM_PROVIDER_ORDER but has no API key; skipping it", name)
    if not slots:
        raise ConfigurationError(
            "No LLM provider has an API key; set OPENAI_API_KEY and/or OPENROUTER_API_KEY"
        )
    return FallbackLLMProvider(slots, settings.llm_max_retries, settings.llm_retry_base_delay_seconds)


def build_retriever(settings: Settings, keyword: KeywordSearch) -> Retriever:
    """The configured retrieval strategy. Semantic strategies fall back to keyword search when unavailable."""
    baseline = KeywordRetriever(keyword)
    if settings.retriever == "keyword" or settings.load_test_mode:  # no embeddings in a load test
        return baseline
    if settings.retriever not in ("vector", "hybrid"):
        raise ConfigurationError(f"Unknown RETRIEVER {settings.retriever!r}: use keyword, vector or hybrid")
    if not settings.openai_api_key:
        logger.warning(
            "RETRIEVER=%s needs an OpenAI key for embeddings; using keyword search", settings.retriever
        )
        return baseline
    embedder = build_embedder(settings)
    index = PgVectorIndex(create_session_factory(_engine()))
    if settings.retriever == "vector":
        return FallbackRetriever(VectorRetriever(embedder, index, _products()), baseline)
    return FallbackRetriever(HybridRetriever(embedder, index, _products(), keyword), baseline)


def build_embedder(settings: Settings) -> OpenAIEmbedder:
    return OpenAIEmbedder(
        settings.openai_api_key,
        settings.embedding_model,
        settings.llm_timeout_seconds,
        settings.embedding_batch_size,
    )


@lru_cache
def build_agent() -> SalesAgent:
    settings = get_settings()
    products = _products()
    keyword = KeywordSearch(products)
    search_tool = SearchProductsTool(
        build_retriever(settings, keyword),
        keyword.categories(),
        settings.store_currency,
        settings.search_result_limit,
    )
    return SalesAgent(
        llm=_llm(),
        tools=ToolRegistry([search_tool]),
        products=products,
        system_prompt=load_system_prompt(settings.prompt_version),
        max_tool_rounds=settings.max_tool_rounds,
        store_info=FileStoreInfoSource(Path(settings.knowledge_path)),
        catalog_overview=render_catalog_overview(products.all(), settings.store_currency),
    )


@lru_cache
def _llm() -> LLMProvider:
    """ONE provider chain for the whole app (agent and summariser share its HTTP clients)."""
    return build_llm(get_settings())


@lru_cache
def build_recording_gateway() -> RecordingGateway:
    """Load-test mode only: a gateway that records instead of sending."""
    return RecordingGateway()


@lru_cache
def _gateway() -> MessagingGateway:
    settings = get_settings()
    if settings.load_test_mode:
        return build_recording_gateway()
    return WahaGateway(
        settings.waha_url, settings.waha_api_key, settings.waha_session, settings.waha_timeout_seconds
    )


@lru_cache
def build_handoff_service() -> HandoffService:
    settings = get_settings()
    store = CachedHandoffStore(
        PostgresHandoffStore(create_session_factory(_engine())),
        _redis(),
        ttl_seconds=int(settings.handoff_timeout_hours * 3600),
    )
    notifiers: list[StaffNotifier] = [LogStaffNotifier()]
    if settings.staff_phone:  # only ever the one configured number
        notifiers.append(WhatsAppStaffNotifier(_gateway(), f"{settings.staff_phone.lstrip('+')}@c.us"))
    return HandoffService(store, CompositeStaffNotifier(notifiers), settings.handoff_timeout_hours)


@lru_cache
def build_returning_customer_service() -> ReturningCustomerService:
    settings = get_settings()
    sessions = create_session_factory(_engine())
    return ReturningCustomerService(
        profiles=PostgresProfileStore(sessions),
        conversations=PostgresConversationStore(sessions),
        summarizer=LLMProfileSummarizer(_llm()),
        summary_max_chars=settings.profile_summary_max_chars,
        shown_limit=settings.profile_products_shown_limit,
        summary_wait_seconds=settings.profile_summary_wait_seconds,
    )


@lru_cache
def build_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        agent=build_agent(),
        memory=build_memory_service(),
        sessions=RedisSessionStore(_redis(), settings.session_ttl_seconds),
        policy=DiscoveryPolicy(settings.max_discovery_questions, settings.session_products_shown_limit),
        follow_ups=PostgresFollowUpStore(create_session_factory(_engine())),
        handoffs=build_handoff_service(),
        returning=build_returning_customer_service(),
        store_url=settings.store_url,
    )


@lru_cache
def build_incoming_message_service() -> IncomingMessageService:
    settings = get_settings()
    gateway = _gateway()
    sender = ReplySender(
        gateway,
        RedisRateLimiter(_redis(), settings.send_rate_limit_per_minute),
        settings.max_bubbles,
        settings.typing_seconds_per_char,
        settings.typing_max_delay_seconds,
    )
    cards = ProductCardFactory(_products(), settings.store_url, settings.store_currency)
    replies = ReplyService(build_chat_service(), gateway, sender, cards)
    debouncer = Debouncer(
        buffer=RedisMessageBuffer(_redis()),
        lock=RedisChatLock(_redis(), settings.lock_ttl_seconds * 1000),
        process=replies.reply,
        quiet_seconds=settings.debounce_seconds,
        lock_wait_seconds=settings.lock_wait_seconds,
        renew_every_seconds=settings.lock_ttl_seconds / LOCK_RENEWALS_PER_TTL,
    )
    return IncomingMessageService(
        gateway=gateway,
        idempotency=RedisIdempotencyStore(_redis(), settings.webhook_dedup_ttl_seconds),
        debouncer=debouncer,
        handoffs=build_handoff_service(),
        allowed_numbers=settings.allowed_number_set,
    )


async def init_storage() -> None:
    """Startup hook: make sure the Postgres tables (and, when available, the pgvector table) exist."""
    await create_tables(_engine())
    await ensure_vector_support(_engine())


async def close_storage() -> None:
    """Shutdown hook: release database and Redis connections."""
    await _engine().dispose()
    await _redis().aclose()
