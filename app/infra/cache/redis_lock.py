"""ChatLock adapter: `SET key token NX PX ttl`, released only by the token's owner."""

import uuid

from redis.asyncio import Redis
from redis.exceptions import WatchError


class RedisChatLock:
    def __init__(self, client: Redis, ttl_ms: int) -> None:
        self._client = client
        self._ttl_ms = ttl_ms

    @staticmethod
    def _key(chat_id: str) -> str:
        return f"lock:chat:{chat_id}"

    async def acquire(self, chat_id: str) -> str | None:
        token = uuid.uuid4().hex
        taken = await self._client.set(self._key(chat_id), token, nx=True, px=self._ttl_ms)
        return token if taken else None

    async def release(self, chat_id: str, token: str) -> None:
        """Compare-and-delete: if our lock expired and someone else took it, we must not free theirs."""
        key = self._key(chat_id)
        async with self._client.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                if await pipe.get(key) == token:
                    pipe.multi()  # type: ignore[no-untyped-call]
                    pipe.delete(key)
                    await pipe.execute()
            except WatchError:
                pass  # the key changed under us: it is no longer ours to delete
