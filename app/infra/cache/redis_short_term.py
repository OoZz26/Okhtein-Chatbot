"""ShortTermMemory adapter: one Redis list per chat, trimmed to N, with a sliding TTL."""

import json

from redis.asyncio import Redis

from app.domain.models import ChatMessage


class RedisShortTermMemory:
    def __init__(self, client: Redis, max_messages: int, ttl_seconds: int) -> None:
        self._client = client
        self._max_messages = max_messages
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(chat_id: str) -> str:
        return f"chat:{chat_id}:history"

    async def append(self, chat_id: str, message: ChatMessage) -> None:
        key = self._key(chat_id)
        payload = json.dumps({"role": message.role, "content": message.content}, ensure_ascii=False)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.rpush(key, payload)
            pipe.ltrim(key, -self._max_messages, -1)
            pipe.expire(key, self._ttl_seconds)  # renewed on every write: a sliding TTL
            await pipe.execute()

    async def recent(self, chat_id: str, limit: int) -> list[ChatMessage]:
        raw_items = await self._client.lrange(self._key(chat_id), -limit, -1)
        items = [json.loads(raw) for raw in raw_items]
        return [ChatMessage(item["role"], item["content"]) for item in items]

    async def clear(self, chat_id: str) -> None:
        await self._client.delete(self._key(chat_id))
