"""Facade over the two-tier memory: Postgres is the source of truth, Redis is a fast cache."""

from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.clock import utc_now
from app.domain.models import ChatMessage
from app.domain.ports import ConversationStore, ShortTermMemory


class MemoryService:
    def __init__(
        self,
        short_term: ShortTermMemory,
        store: ConversationStore,
        history_limit: int,
        session_ttl_seconds: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._short_term = short_term
        self._store = store
        self._history_limit = history_limit
        self._session_ttl = timedelta(seconds=session_ttl_seconds)
        self._clock = clock

    async def record(self, chat_id: str, message: ChatMessage, display_name: str = "") -> None:
        """Write-through: Postgres first (never lose a message), then the Redis cache."""
        now = self._clock()
        await self._store.upsert_customer(chat_id, display_name, now)
        await self._store.save_message(chat_id, message, now)
        await self._short_term.append(chat_id, message)

    async def context(self, chat_id: str) -> list[ChatMessage]:
        """Cache-aside: Redis first; on a miss rebuild from Postgres if the session is still alive."""
        recent = await self._short_term.recent(chat_id, self._history_limit)
        if recent:
            return recent
        if not await self._session_is_alive(chat_id):
            return []
        reloaded = await self._store.recent_messages(chat_id, self._history_limit)
        for message in reloaded:
            await self._short_term.append(chat_id, message)
        return reloaded

    async def _session_is_alive(self, chat_id: str) -> bool:
        last = await self._store.last_message_at(chat_id)
        return last is not None and self._clock() - last <= self._session_ttl
