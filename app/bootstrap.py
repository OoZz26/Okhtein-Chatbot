"""Composition root: the ONE place where concrete classes are chosen and wired together."""

import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.discovery import DiscoveryPolicy
from app.domain.errors import ConfigurationError
from app.domain.llm.fallback_chain import FallbackLLMProvider, ProviderSlot
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.tools.base import ToolRegistry
from app.domain.tools.search_products import SearchProductsTool
from app.infra.cache.redis_buffer import RedisMessageBuffer
from app.infra.cache.redis_idempotency import RedisIdempotencyStore
from app.infra.cache.redis_lock import RedisChatLock
from app.infra.cache.redis_rate_limiter import RedisRateLimiter
from app.infra.cache.redis_session_store import RedisSessionStore
from app.infra.cache.redis_short_term import RedisShortTermMemory
from app.infra.catalog.file_store_info import FileStoreInfoSource
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.db.conversation_store import PostgresConversationStore
from app.infra.db.follow_up_store import PostgresFollowUpStore
from app.infra.db.session import create_engine, create_session_factory, create_tables
from app.infra.llm.openai_provider import OpenAICompatibleProvider
from app.infra.whatsapp.waha_gateway import WahaGateway
from app.services.chat_service import ChatService
from app.services.debouncer import Debouncer
from app.services.incoming_message_service import IncomingMessageService
from app.services.memory_service import MemoryService
from app.services.product_cards import ProductCardFactory
from app.services.reply_sender import ReplySender
from app.services.reply_service import ReplyService

logger = logging.getLogger(__name__)


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
        settings.openai_api_key, settings.openai_model, settings.llm_timeout_seconds
    )


def _openrouter(settings: Settings) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.llm_timeout_seconds,
        base_url=settings.openrouter_base_url,
        headers={"X-Title": "Okhtein WhatsApp Assistant"},
    )


def build_llm(settings: Settings) -> FallbackLLMProvider:
    """The provider chain, in the configured order. Providers without an API key are skipped."""
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


@lru_cache
def build_agent() -> SalesAgent:
    settings = get_settings()
    products = _products()
    search_tool = SearchProductsTool(
        KeywordSearch(products), settings.store_currency, settings.search_result_limit
    )
    return SalesAgent(
        llm=build_llm(settings),
        tools=ToolRegistry([search_tool]),
        products=products,
        system_prompt=load_system_prompt(settings.prompt_version),
        max_tool_rounds=settings.max_tool_rounds,
        store_info=FileStoreInfoSource(Path(settings.knowledge_path)),
    )


@lru_cache
def build_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        agent=build_agent(),
        memory=build_memory_service(),
        sessions=RedisSessionStore(_redis(), settings.session_ttl_seconds),
        policy=DiscoveryPolicy(settings.max_discovery_questions),
        follow_ups=PostgresFollowUpStore(create_session_factory(_engine())),
        store_url=settings.store_url,
    )


@lru_cache
def build_incoming_message_service() -> IncomingMessageService:
    settings = get_settings()
    gateway = WahaGateway(
        settings.waha_url, settings.waha_api_key, settings.waha_session, settings.waha_timeout_seconds
    )
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
    )
    return IncomingMessageService(
        gateway=gateway,
        idempotency=RedisIdempotencyStore(_redis(), settings.webhook_dedup_ttl_seconds),
        debouncer=debouncer,
        allowed_numbers=settings.allowed_number_set,
    )


async def init_storage() -> None:
    """Startup hook: make sure the Postgres tables exist."""
    await create_tables(_engine())


async def close_storage() -> None:
    """Shutdown hook: release database and Redis connections."""
    await _engine().dispose()
    await _redis().aclose()
