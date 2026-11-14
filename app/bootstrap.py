"""Composition root: the ONE place where concrete classes are chosen and wired together."""

from functools import lru_cache
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import ConfigurationError
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.tools.base import ToolRegistry
from app.domain.tools.search_products import SearchProductsTool
from app.infra.cache.redis_idempotency import RedisIdempotencyStore
from app.infra.cache.redis_short_term import RedisShortTermMemory
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.db.conversation_store import PostgresConversationStore
from app.infra.db.session import create_engine, create_session_factory, create_tables
from app.infra.llm.openai_provider import OpenAIProvider
from app.infra.whatsapp.waha_gateway import WahaGateway
from app.services.chat_service import ChatService
from app.services.incoming_message_service import IncomingMessageService
from app.services.memory_service import MemoryService


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
def build_memory_service() -> MemoryService:
    settings = get_settings()
    return MemoryService(
        short_term=RedisShortTermMemory(_redis(), settings.history_limit, settings.session_ttl_seconds),
        store=PostgresConversationStore(create_session_factory(_engine())),
        history_limit=settings.history_limit,
        session_ttl_seconds=settings.session_ttl_seconds,
    )


@lru_cache
def build_chat_service() -> ChatService:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ConfigurationError("OPENAI_API_KEY is not set; add it to your .env file")
    products = JsonProductRepository(Path(settings.products_path))
    search_tool = SearchProductsTool(
        KeywordSearch(products), settings.store_currency, settings.search_result_limit
    )
    agent = SalesAgent(
        llm=OpenAIProvider(settings.openai_api_key, settings.openai_model, settings.llm_timeout_seconds),
        tools=ToolRegistry([search_tool]),
        products=products,
        system_prompt=load_system_prompt(),
        max_tool_rounds=settings.max_tool_rounds,
    )
    return ChatService(agent, build_memory_service(), settings.store_url)


@lru_cache
def build_incoming_message_service() -> IncomingMessageService:
    settings = get_settings()
    return IncomingMessageService(
        chat_service=build_chat_service(),
        gateway=WahaGateway(
            settings.waha_url, settings.waha_api_key, settings.waha_session, settings.waha_timeout_seconds
        ),
        idempotency=RedisIdempotencyStore(_redis(), settings.webhook_dedup_ttl_seconds),
        allowed_numbers=settings.allowed_number_set,
    )


async def init_storage() -> None:
    """Startup hook: make sure the Postgres tables exist."""
    await create_tables(_engine())


async def close_storage() -> None:
    """Shutdown hook: release database and Redis connections."""
    await _engine().dispose()
    await _redis().aclose()
