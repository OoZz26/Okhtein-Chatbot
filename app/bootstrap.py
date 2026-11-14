"""Composition root: the ONE place where concrete classes are chosen and wired together."""

from functools import lru_cache
from pathlib import Path

from redis.asyncio import Redis

from app.core.config import get_settings
from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import ConfigurationError
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.tools.base import ToolRegistry
from app.domain.tools.search_products import SearchProductsTool
from app.infra.cache.redis_idempotency import RedisIdempotencyStore
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.llm.openai_provider import OpenAIProvider
from app.infra.whatsapp.waha_gateway import WahaGateway
from app.services.chat_service import ChatService
from app.services.incoming_message_service import IncomingMessageService


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
    return ChatService(agent, settings.store_url)


@lru_cache
def build_incoming_message_service() -> IncomingMessageService:
    settings = get_settings()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return IncomingMessageService(
        chat_service=build_chat_service(),
        gateway=WahaGateway(
            settings.waha_url, settings.waha_api_key, settings.waha_session, settings.waha_timeout_seconds
        ),
        idempotency=RedisIdempotencyStore(redis_client, settings.webhook_dedup_ttl_seconds),
        allowed_numbers=settings.allowed_number_set,
    )
