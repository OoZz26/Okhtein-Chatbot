"""Async SQLAlchemy engine and session factory for Postgres."""

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.infra.db.models import Base


def create_engine(host: str, port: int, user: str, password: str, database: str) -> AsyncEngine:
    url = URL.create("postgresql+asyncpg", user, password, host, port, database)  # quotes odd characters
    return create_async_engine(url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    """Create missing tables at startup. (A migration tool such as Alembic is a 'Later' item.)"""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # create_all never alters an existing table, so columns added later are patched in here.
        await connection.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS profile JSONB"))
