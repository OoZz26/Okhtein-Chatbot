"""MessageBuffer adapter: a Redis list of the burst, plus a counter that numbers each push."""

from redis.asyncio import Redis

BUFFER_TTL_SECONDS = 3600  # a safety net: an abandoned buffer must not live forever


class RedisMessageBuffer:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def _buffer_key(chat_id: str) -> str:
        return f"chat:{chat_id}:buffer"

    @staticmethod
    def _sequence_key(chat_id: str) -> str:
        return f"chat:{chat_id}:buffer:seq"

    async def push(self, chat_id: str, text: str) -> int:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.rpush(self._buffer_key(chat_id), text)
            pipe.expire(self._buffer_key(chat_id), BUFFER_TTL_SECONDS)
            pipe.incr(self._sequence_key(chat_id))
            pipe.expire(self._sequence_key(chat_id), BUFFER_TTL_SECONDS)
            results = await pipe.execute()
        return int(results[2])

    async def latest_sequence(self, chat_id: str) -> int:
        raw = await self._client.get(self._sequence_key(chat_id))
        return int(raw) if raw is not None else 0

    async def drain(self, chat_id: str) -> list[str]:
        """LRANGE + DEL inside one MULTI/EXEC, so nothing pushed meanwhile is lost or read twice."""
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.lrange(self._buffer_key(chat_id), 0, -1)
            pipe.delete(self._buffer_key(chat_id))
            results = await pipe.execute()
        return [str(item) for item in results[0]]
