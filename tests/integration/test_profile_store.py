"""Long-term profile and message history against the REAL Postgres. Run with: pytest -m integration."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.domain.discovery import CustomerProfile
from app.domain.long_term_profile import LongTermProfile
from app.domain.models import ChatMessage
from app.infra.db.conversation_store import PostgresConversationStore
from app.infra.db.models import CustomerRow, MessageRow
from app.infra.db.profile_store import PostgresProfileStore
from app.infra.db.session import create_engine, create_session_factory, create_tables

pytestmark = pytest.mark.integration

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    s = get_settings()
    eng = create_engine(s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db)
    await create_tables(eng)
    yield eng
    await eng.dispose()


async def test_the_profile_round_trips_through_the_customers_table(engine: AsyncEngine) -> None:
    chat = f"it-{uuid.uuid4().hex[:12]}@c.us"
    sessions = create_session_factory(engine)
    store = PostgresProfileStore(sessions, clock=lambda: NOW)
    assert (await store.get(chat)).is_empty

    profile = LongTermProfile(
        slots=CustomerProfile(colour="ذهبي", occasion="wedding"),
        summary="Likes bold gold pieces.",
        products_shown=("lotus-clutch", "bond-ring"),
        summarized_until=NOW,
        updated_at=NOW,
    )
    await store.save(chat, profile)

    assert await store.get(chat) == profile  # including the Arabic slot value and the timestamps
    async with sessions.begin() as session:
        await session.execute(delete(CustomerRow).where(CustomerRow.chat_id == chat))


async def test_saving_a_profile_does_not_wipe_the_customer_record_and_vice_versa(
    engine: AsyncIterator,
) -> None:
    chat = f"it-{uuid.uuid4().hex[:12]}@c.us"
    sessions = create_session_factory(engine)
    conversations = PostgresConversationStore(sessions)
    profiles = PostgresProfileStore(sessions)

    await conversations.upsert_customer(chat, "Sara", NOW)
    await profiles.save(chat, LongTermProfile(summary="Likes gold."))
    await conversations.upsert_customer(chat, "", NOW + timedelta(days=1))  # a later message, no name

    assert (await profiles.get(chat)).summary == "Likes gold."  # the profile survived the customer upsert
    async with sessions() as session:
        row = await session.get(CustomerRow, chat)
    assert row is not None and row.display_name == "Sara"  # and the name survived the profile save

    async with sessions.begin() as session:
        await session.execute(delete(CustomerRow).where(CustomerRow.chat_id == chat))


async def test_messages_after_returns_only_what_is_newer_oldest_first(engine: AsyncEngine) -> None:
    chat = f"it-{uuid.uuid4().hex[:12]}@c.us"
    sessions = create_session_factory(engine)
    store = PostgresConversationStore(sessions)
    for minutes, text_ in enumerate(["one", "two", "three"]):
        await store.save_message(chat, ChatMessage("user", text_), NOW + timedelta(minutes=minutes))

    everything = await store.messages_after(chat, None, 10)
    newer = await store.messages_after(chat, NOW + timedelta(minutes=0), 10)

    assert [m.content for m in everything] == ["one", "two", "three"]
    assert [m.content for m in newer] == ["two", "three"]
    async with sessions.begin() as session:
        await session.execute(delete(MessageRow).where(MessageRow.chat_id == chat))


async def test_the_profile_column_is_added_to_an_existing_customers_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS profile"))
    await create_tables(engine)  # what the app does at startup

    async with engine.connect() as connection:
        found = (
            await connection.execute(
                text(
                    "select data_type from information_schema.columns "
                    "where table_name = 'customers' and column_name = 'profile'"
                )
            )
        ).scalar_one()
    assert found == "jsonb"
