"""Memory against the REAL Docker services. Run with: pytest -m integration (needs `docker compose up -d`)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.domain.models import ChatMessage
from app.infra.cache.redis_short_term import RedisShortTermMemory
from app.infra.db.conversation_store import PostgresConversationStore
from app.infra.db.models import CustomerRow, MessageRow
from app.infra.db.session import create_engine, create_session_factory, create_tables
from app.services.memory_service import MemoryService

pytestmark = pytest.mark.integration

TEST_REDIS_DB = 15  # a scratch database, so the tests never touch real conversations


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    s = get_settings()
    eng = create_engine(s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db)
    await create_tables(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    s = get_settings()
    client = Redis(host=s.redis_host, port=s.redis_port, db=TEST_REDIS_DB, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def chat_id() -> str:
    return f"it-{uuid.uuid4().hex[:12]}@c.us"


def build_memory(engine: AsyncEngine, redis_client: Redis) -> MemoryService:
    s = get_settings()
    return MemoryService(
        RedisShortTermMemory(redis_client, s.history_limit, s.session_ttl_seconds),
        PostgresConversationStore(create_session_factory(engine)),
        s.history_limit,
        s.session_ttl_seconds,
    )


async def test_messages_land_in_postgres_with_chat_id_role_and_time(
    engine: AsyncEngine, redis_client: Redis, chat_id: str
) -> None:
    memory = build_memory(engine, redis_client)
    await memory.record(chat_id, ChatMessage("user", "I want a clutch"), "Integration Tester")
    await memory.record(chat_id, ChatMessage("assistant", "Here you go ✨"))

    async with create_session_factory(engine)() as session:
        rows = (
            (await session.execute(select(MessageRow).where(MessageRow.chat_id == chat_id))).scalars().all()
        )
        customer = await session.get(CustomerRow, chat_id)
    assert [(r.role, r.content) for r in rows] == [
        ("user", "I want a clutch"),
        ("assistant", "Here you go ✨"),
    ]
    assert all(r.created_at is not None for r in rows)
    assert customer is not None and customer.display_name == "Integration Tester"

    async with create_session_factory(engine).begin() as session:  # clean up our test rows
        await session.execute(delete(MessageRow).where(MessageRow.chat_id == chat_id))
        await session.execute(delete(CustomerRow).where(CustomerRow.chat_id == chat_id))


async def test_flushing_redis_keeps_the_context_and_a_restart_does_too(
    engine: AsyncEngine, redis_client: Redis, chat_id: str
) -> None:
    first_run = build_memory(engine, redis_client)
    await first_run.record(chat_id, ChatMessage("user", "I want a clutch"))
    await first_run.record(chat_id, ChatMessage("assistant", "Try the Lotus Clutch"))

    await redis_client.flushdb()  # Redis lost everything...
    restarted_app = build_memory(engine, redis_client)  # ...and the app restarted

    context = await restarted_app.context(chat_id)

    assert [m.content for m in context] == ["I want a clutch", "Try the Lotus Clutch"]
    assert await redis_client.llen(f"chat:{chat_id}:history") == 2  # cache refilled

    async with create_session_factory(engine).begin() as session:
        await session.execute(delete(MessageRow).where(MessageRow.chat_id == chat_id))
        await session.execute(delete(CustomerRow).where(CustomerRow.chat_id == chat_id))
