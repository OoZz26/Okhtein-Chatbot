from fakeredis import FakeAsyncRedis

from app.infra.cache.redis_buffer import RedisMessageBuffer
from app.infra.cache.redis_lock import RedisChatLock
from app.infra.cache.redis_rate_limiter import RedisRateLimiter

CHAT = "chat-1"


def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


class TestRedisMessageBuffer:
    async def test_push_numbers_messages_and_drain_returns_them_in_order_once(self) -> None:
        buffer = RedisMessageBuffer(redis())

        assert await buffer.push(CHAT, "hi") == 1
        assert await buffer.push(CHAT, "I want a bag") == 2
        assert await buffer.latest_sequence(CHAT) == 2

        assert await buffer.drain(CHAT) == ["hi", "I want a bag"]
        assert await buffer.drain(CHAT) == []  # drained messages are never returned twice

    async def test_sequences_are_per_chat(self) -> None:
        buffer = RedisMessageBuffer(redis())
        await buffer.push("a", "x")

        assert await buffer.latest_sequence("b") == 0


class TestRedisChatLock:
    async def test_only_one_holder_at_a_time(self) -> None:
        lock = RedisChatLock(redis(), ttl_ms=5000)

        token = await lock.acquire(CHAT)

        assert token is not None
        assert await lock.acquire(CHAT) is None
        await lock.release(CHAT, token)
        assert await lock.acquire(CHAT) is not None

    async def test_a_stale_token_cannot_release_someone_elses_lock(self) -> None:
        client = redis()
        lock = RedisChatLock(client, ttl_ms=5000)
        await lock.acquire(CHAT)

        await lock.release(CHAT, "not-the-owner")

        assert await client.exists("lock:chat:chat-1") == 1  # still held by the real owner

    async def test_the_lock_expires_by_itself(self) -> None:
        client = redis()
        lock = RedisChatLock(client, ttl_ms=5000)
        await lock.acquire(CHAT)

        assert 0 < await client.pttl("lock:chat:chat-1") <= 5000  # a crashed worker cannot block forever


class TestRedisRateLimiter:
    async def test_sends_within_the_limit_are_free_then_callers_must_wait(self) -> None:
        now = 1_000_030.0  # 30 seconds into a minute
        limiter = RedisRateLimiter(redis(), per_minute=2, clock=lambda: now)

        assert await limiter.seconds_until_allowed() == 0.0
        assert await limiter.seconds_until_allowed() == 0.0
        wait = await limiter.seconds_until_allowed()

        assert 0 < wait <= 60  # until the next minute starts

    async def test_a_new_window_starts_fresh(self) -> None:
        clock = {"now": 1_000_030.0}
        limiter = RedisRateLimiter(redis(), per_minute=1, clock=lambda: clock["now"])
        await limiter.seconds_until_allowed()
        assert await limiter.seconds_until_allowed() > 0

        clock["now"] += 61

        assert await limiter.seconds_until_allowed() == 0.0
