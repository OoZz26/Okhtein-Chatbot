"""VectorIndex adapter: product embeddings in Postgres with the pgvector extension."""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.errors import RetrievalError
from app.domain.models import IndexedProduct, ScoredHandle, VectorFilters
from app.infra.db.vector_models import ProductEmbeddingRow, VectorBase

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def ensure_vector_support(engine: AsyncEngine) -> bool:
    """Create the extension, the table and the HNSW index. Returns False (and logs) if pgvector is missing,
    so the app still starts and retrieval falls back to keyword search."""
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.run_sync(VectorBase.metadata.create_all)
    except SQLAlchemyError as exc:
        logger.warning("pgvector is not available; semantic search is off, keyword search stays on: %s", exc)
        return False
    return True


class PgVectorIndex:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def upsert(self, items: Sequence[IndexedProduct]) -> None:
        if not items:
            return
        rows = [
            {
                "handle": item.handle,
                "content_hash": item.content_hash,
                "embedding_model": item.embedding_model,
                "category": item.category,
                "price_min": item.price_min,
                "available": item.available,
                "title": item.title,
                "embedding": list(item.embedding),
                "updated_at": self._clock(),
            }
            for item in items
        ]
        statement = insert(ProductEmbeddingRow).values(rows)
        changed = {name: statement.excluded[name] for name in rows[0] if name != "handle"}
        async with self._session_factory.begin() as session:
            await session.execute(statement.on_conflict_do_update(index_elements=["handle"], set_=changed))

    async def search(self, vector: Sequence[float], filters: VectorFilters, k: int) -> list[ScoredHandle]:
        """Filters and similarity ranking in ONE query: WHERE ... ORDER BY embedding <=> :vector LIMIT k."""
        distance = ProductEmbeddingRow.embedding.cosine_distance(list(vector))
        query = select(ProductEmbeddingRow.handle, distance.label("distance"))
        if filters.in_stock_only:
            query = query.where(ProductEmbeddingRow.available.is_(True))
        if filters.max_price is not None:
            query = query.where(ProductEmbeddingRow.price_min <= filters.max_price)
        if filters.category:
            query = query.where(ProductEmbeddingRow.category.ilike(f"%{filters.category}%"))
        query = query.order_by(distance).limit(k)
        try:
            async with self._session_factory() as session:
                rows = (await session.execute(query)).all()
        except SQLAlchemyError as exc:
            raise RetrievalError(f"Vector search failed: {exc}") from exc
        return [ScoredHandle(handle, 1.0 - float(dist)) for handle, dist in rows]

    async def indexed_hashes(self) -> dict[str, tuple[str, str]]:
        query = select(
            ProductEmbeddingRow.handle, ProductEmbeddingRow.content_hash, ProductEmbeddingRow.embedding_model
        )
        async with self._session_factory() as session:
            rows = (await session.execute(query)).all()
        return {handle: (content_hash, model) for handle, content_hash, model in rows}

    async def delete(self, handles: Sequence[str]) -> None:
        if not handles:
            return
        async with self._session_factory.begin() as session:
            await session.execute(delete(ProductEmbeddingRow).where(ProductEmbeddingRow.handle.in_(handles)))
