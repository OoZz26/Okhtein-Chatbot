"""The handoff episodes against the REAL Postgres. Run with: pytest -m integration."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.domain.handoff import HandoffState
from app.infra.db.handoff_store import PostgresHandoffStore
from app.infra.db.models import HandoffRow
from app.infra.db.session import create_engine, create_session_factory, create_tables

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    s = get_settings()
    eng = create_engine(s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db)
    await create_tables(eng)
    yield eng
    await eng.dispose()


async def test_handoff_and_release_are_recorded_as_episodes(engine: AsyncEngine) -> None:
    chat = f"it-{uuid.uuid4().hex[:12]}@c.us"
    sessions = create_session_factory(engine)
    store = PostgresHandoffStore(sessions)
    assert not (await store.get(chat)).is_handed_off

    await store.save(chat, HandoffState().handoff("order tracking", "Where is order 1?", datetime.now(UTC)))
    state = await store.get(chat)
    assert (state.is_handed_off, state.reason, state.summary) == (True, "order tracking", "Where is order 1?")

    await store.save(chat, HandoffState())  # release
    assert not (await store.get(chat)).is_handed_off

    await store.save(
        chat, HandoffState().handoff("complaint", "Damaged", datetime.now(UTC))
    )  # a second episode
    assert (await store.get(chat)).reason == "complaint"

    async with sessions() as session:
        rows = (await session.execute(select(HandoffRow).where(HandoffRow.chat_id == chat))).scalars().all()
    assert [(r.reason, r.released_at is not None) for r in rows] == [
        ("order tracking", True),
        ("complaint", False),
    ]

    async with sessions.begin() as session:  # clean up our test rows
        await session.execute(delete(HandoffRow).where(HandoffRow.chat_id == chat))
