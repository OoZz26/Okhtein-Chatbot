"""HandoffStore adapter: handoff episodes in Postgres (the source of truth)."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import utc_now
from app.domain.handoff import ChatMode, HandoffState
from app.infra.db.models import HandoffRow


class PostgresHandoffStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def get(self, chat_id: str) -> HandoffState:
        query = (
            select(HandoffRow).where(HandoffRow.chat_id == chat_id).order_by(HandoffRow.id.desc()).limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).scalar_one_or_none()
        if row is None or row.released_at is not None:
            return HandoffState()
        return HandoffState(ChatMode.HANDED_OFF, row.reason, row.summary, row.created_at)

    async def save(self, chat_id: str, state: HandoffState) -> None:
        async with self._session_factory.begin() as session:
            if state.is_handed_off:
                session.add(
                    HandoffRow(
                        chat_id=chat_id,
                        reason=state.reason[:255],
                        summary=state.summary,
                        created_at=state.since or self._clock(),
                    )
                )
            else:
                open_episodes = (HandoffRow.chat_id == chat_id) & (HandoffRow.released_at.is_(None))
                await session.execute(
                    update(HandoffRow).where(open_episodes).values(released_at=self._clock())
                )
