"""ConversationStore adapter: customers and messages in Postgres."""

from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.models import ChatMessage, Role
from app.infra.db.models import CustomerRow, MessageRow


class PostgresConversationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert_customer(self, chat_id: str, display_name: str, seen_at: datetime) -> None:
        statement = insert(CustomerRow).values(
            chat_id=chat_id, display_name=display_name, first_seen=seen_at, last_seen=seen_at
        )
        updates: dict[str, object] = {"last_seen": seen_at}
        if display_name:  # never overwrite a known name with an empty one
            updates["display_name"] = display_name
        async with self._session_factory.begin() as session:
            await session.execute(statement.on_conflict_do_update(index_elements=["chat_id"], set_=updates))

    async def save_message(self, chat_id: str, message: ChatMessage, created_at: datetime) -> None:
        row = MessageRow(chat_id=chat_id, role=message.role, content=message.content, created_at=created_at)
        async with self._session_factory.begin() as session:
            session.add(row)

    async def last_message_at(self, chat_id: str) -> datetime | None:
        query = select(func.max(MessageRow.created_at)).where(MessageRow.chat_id == chat_id)
        async with self._session_factory() as session:
            return (await session.execute(query)).scalar()

    async def recent_messages(self, chat_id: str, limit: int) -> list[ChatMessage]:
        query = (
            select(MessageRow)
            .where(MessageRow.chat_id == chat_id)
            .order_by(MessageRow.id.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(query)).scalars().all()
        return [ChatMessage(cast(Role, row.role), row.content) for row in reversed(rows)]
