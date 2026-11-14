"""A caching decorator for any HandoffStore: Redis answers the 'is it handed off?' check on every message."""

import json
from datetime import datetime

from redis.asyncio import Redis

from app.domain.handoff import ChatMode, HandoffState
from app.domain.ports import HandoffStore


class CachedHandoffStore:
    """Write-through, cache-aside: the wrapped store stays the source of truth, Redis is disposable."""

    def __init__(self, inner: HandoffStore, client: Redis, ttl_seconds: int) -> None:
        self._inner = inner
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(chat_id: str) -> str:
        return f"chat:{chat_id}:handoff"

    async def get(self, chat_id: str) -> HandoffState:
        raw = await self._client.get(self._key(chat_id))
        if raw is not None:
            return self._decode(raw)
        state = await self._inner.get(chat_id)
        await self._cache(chat_id, state)
        return state

    async def save(self, chat_id: str, state: HandoffState) -> None:
        await self._inner.save(chat_id, state)
        await self._cache(chat_id, state)

    async def _cache(self, chat_id: str, state: HandoffState) -> None:
        payload = {
            "mode": state.mode.value,
            "reason": state.reason,
            "summary": state.summary,
            "since": state.since.isoformat() if state.since else None,
        }
        await self._client.set(
            self._key(chat_id), json.dumps(payload, ensure_ascii=False), ex=self._ttl_seconds
        )

    @staticmethod
    def _decode(raw: str | bytes) -> HandoffState:
        data = json.loads(raw)
        since = datetime.fromisoformat(data["since"]) if data["since"] else None
        return HandoffState(ChatMode(data["mode"]), data["reason"], data["summary"], since)
