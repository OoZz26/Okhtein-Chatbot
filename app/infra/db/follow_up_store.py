"""FollowUpStore adapter: one row per flagged chat in Postgres."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.db.models import FollowUpRow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PostgresFollowUpStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def flag(self, chat_id: str, reason: str) -> None:
        row = FollowUpRow(chat_id=chat_id, reason=reason[:255], created_at=self._clock(), resolved=False)
        async with self._session_factory.begin() as session:
            session.add(row)
