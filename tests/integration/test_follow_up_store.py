"""The follow-up flag against the REAL Postgres. Run with: pytest -m integration."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.infra.db.follow_up_store import PostgresFollowUpStore
from app.infra.db.models import FollowUpRow
from app.infra.db.session import create_engine, create_session_factory, create_tables

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    s = get_settings()
    eng = create_engine(s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db)
    await create_tables(eng)
    yield eng
    await eng.dispose()


async def test_a_flagged_chat_is_stored_unresolved(engine: AsyncEngine) -> None:
    chat_id = f"it-{uuid.uuid4().hex[:12]}@c.us"
    sessions = create_session_factory(engine)

    await PostgresFollowUpStore(sessions).flag(chat_id, "assistant unavailable")

    async with sessions() as session:
        rows = (
            (await session.execute(select(FollowUpRow).where(FollowUpRow.chat_id == chat_id))).scalars().all()
        )
    assert [(r.reason, r.resolved) for r in rows] == [("assistant unavailable", False)]
    assert rows[0].created_at is not None

    async with sessions.begin() as session:  # clean up our test row
        await session.execute(delete(FollowUpRow).where(FollowUpRow.chat_id == chat_id))
