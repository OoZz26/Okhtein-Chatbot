"""RateLimiter adapter: a fixed window counter per minute, shared by every sender."""

import time
from collections.abc import Callable

from redis.asyncio import Redis

WINDOW_SECONDS = 60


class RedisRateLimiter:
    def __init__(self, client: Redis, per_minute: int, clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._per_minute = per_minute
        self._clock = clock

    async def seconds_until_allowed(self) -> float:
        now = self._clock()
        window = int(now // WINDOW_SECONDS)
        key = f"ratelimit:send:{window}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS * 2)
            count = int((await pipe.execute())[0])
        if count <= self._per_minute:
            return 0.0
        return (window + 1) * WINDOW_SECONDS - now  # wait for the next window
