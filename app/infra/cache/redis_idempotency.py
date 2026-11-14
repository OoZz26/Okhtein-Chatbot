"""IdempotencyStore adapter: Redis `SET key value NX EX ttl` is an atomic 'first one wins'."""

from redis.asyncio import Redis

KEY_PREFIX = "idem:"


class RedisIdempotencyStore:
    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def claim(self, key: str) -> bool:
        was_set = await self._client.set(KEY_PREFIX + key, "1", nx=True, ex=self._ttl_seconds)
        return bool(was_set)
