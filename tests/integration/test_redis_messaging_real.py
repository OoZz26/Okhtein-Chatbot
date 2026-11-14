"""Buffer, lock and rate limiter against the REAL Redis (scratch database 15). pytest -m integration."""

import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.infra.cache.redis_buffer import RedisMessageBuffer
from app.infra.cache.redis_lock import RedisChatLock
from app.infra.cache.redis_rate_limiter import RedisRateLimiter

pytestmark = pytest.mark.integration


@pytest.fixture
async def client() -> AsyncIterator[Redis]:
    s = get_settings()
    redis = Redis(host=s.redis_host, port=s.redis_port, db=15, decode_responses=True)
    await redis.flushdb()
    yield redis
    await redis.flushdb()
    await redis.aclose()


async def test_buffer_drain_is_atomic_and_ordered(client: Redis) -> None:
    buffer = RedisMessageBuffer(client)
    chat = f"it-{uuid.uuid4().hex[:8]}"

    assert [await buffer.push(chat, text) for text in ("hi", "a bag", "for a wedding")] == [1, 2, 3]

    assert await buffer.drain(chat) == ["hi", "a bag", "for a wedding"]
    assert await buffer.drain(chat) == []


async def test_lock_is_exclusive_and_owner_checked(client: Redis) -> None:
    lock = RedisChatLock(client, ttl_ms=5000)
    chat = f"it-{uuid.uuid4().hex[:8]}"

    token = await lock.acquire(chat)
    assert token is not None
    assert await lock.acquire(chat) is None  # a second worker cannot enter
    await lock.release(chat, "someone-else")
    assert await lock.acquire(chat) is None  # a wrong token frees nothing
    await lock.release(chat, token)
    assert await lock.acquire(chat) is not None


async def test_rate_limiter_blocks_after_the_limit(client: Redis) -> None:
    limiter = RedisRateLimiter(client, per_minute=3, clock=lambda: 2_000_010.0)

    waits = [await limiter.seconds_until_allowed() for _ in range(5)]

    assert waits[:3] == [0.0, 0.0, 0.0]
    assert all(wait > 0 for wait in waits[3:])
