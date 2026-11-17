"""LongTermProfileStore adapter: the profile lives in customers.profile (JSONB)."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import utc_now
from app.domain.discovery import CustomerProfile
from app.domain.long_term_profile import LongTermProfile
from app.infra.db.models import CustomerRow


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class PostgresProfileStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def get(self, chat_id: str) -> LongTermProfile:
        query = select(CustomerRow.profile).where(CustomerRow.chat_id == chat_id)
        async with self._session_factory() as session:
            data = (await session.execute(query)).scalar_one_or_none()
        if not data:
            return LongTermProfile()
        return LongTermProfile(
            slots=CustomerProfile().apply(data.get("slots", {})),
            summary=data.get("summary", ""),
            products_shown=tuple(data.get("products_shown", ())),
            summarized_until=_parse(data.get("summarized_until")),
            updated_at=_parse(data.get("updated_at")),
        )

    async def save(self, chat_id: str, profile: LongTermProfile) -> None:
        data: dict[str, Any] = {
            "slots": profile.slots.known(),
            "summary": profile.summary,
            "products_shown": list(profile.products_shown),
            "summarized_until": profile.summarized_until.isoformat() if profile.summarized_until else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
        now = self._clock()
        statement = insert(CustomerRow).values(
            chat_id=chat_id, display_name="", first_seen=now, last_seen=now, profile=data
        )
        async with self._session_factory.begin() as session:
            await session.execute(
                statement.on_conflict_do_update(index_elements=["chat_id"], set_={"profile": data})
            )
