"""FollowUpStore adapter: one row per flagged chat in Postgres."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import utc_now
from app.infra.db.models import FollowUpRow


class PostgresFollowUpStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def flag(self, chat_id: str, reason: str) -> None:
        row = FollowUpRow(chat_id=chat_id, reason=reason[:255], created_at=self._clock(), resolved=False)
        async with self._session_factory.begin() as session:
            session.add(row)
