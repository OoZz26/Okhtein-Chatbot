"""The vector index against REAL pgvector. Run with: pytest -m integration."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.domain.models import IndexedProduct, VectorFilters
from app.infra.db.pgvector_index import PgVectorIndex, ensure_vector_support
from app.infra.db.session import create_engine, create_session_factory
from app.infra.db.vector_models import EMBEDDING_DIMENSIONS, ProductEmbeddingRow

pytestmark = pytest.mark.integration


def vector(*leading: float) -> tuple[float, ...]:
    """A 1536-dim vector that starts with `leading` and is zero elsewhere."""
    return (*leading, *([0.0] * (EMBEDDING_DIMENSIONS - len(leading))))


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    s = get_settings()
    eng = create_engine(s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db)
    assert await ensure_vector_support(eng), (
        "this Postgres has no pgvector: use the image from docker-compose.yml"
    )
    yield eng
    await eng.dispose()


def product(prefix: str, name: str, emb: tuple[float, ...], **overrides: object) -> IndexedProduct:
    fields: dict[str, object] = {
        "handle": f"{prefix}-{name}",
        "content_hash": "h",
        "embedding_model": "test-model",
        "category": "Clutch",
        "price_min": 40000.0,
        "available": True,
        "title": name,
        "embedding": emb,
    }
    fields.update(overrides)
    return IndexedProduct(**fields)  # type: ignore[arg-type]


async def test_filters_and_similarity_run_in_one_query(engine: AsyncEngine) -> None:
    prefix = f"it-{uuid.uuid4().hex[:8]}"
    sessions = create_session_factory(engine)
    index = PgVectorIndex(sessions)
    await index.upsert(
        [
            product(prefix, "closest", vector(1.0, 0.0)),
            product(prefix, "close", vector(0.8, 0.6)),
            product(prefix, "far", vector(0.0, 1.0)),
            product(prefix, "pricey", vector(0.99, 0.1), price_min=90000.0),
            product(prefix, "sold-out", vector(0.99, 0.1), available=False),
            product(prefix, "ring", vector(0.99, 0.1), category="Ring"),
        ]
    )
    try:
        wide = await index.search(vector(1.0, 0.0), VectorFilters(), 50)
        ours = [hit for hit in wide if hit.handle.startswith(prefix)]
        assert ours[0].handle == f"{prefix}-closest"
        assert ours[0].score > ours[-1].score  # ordered by similarity, best first

        budget = await index.search(vector(1.0, 0.0), VectorFilters(max_price=50000), 50)
        assert f"{prefix}-pricey" not in [h.handle for h in budget]

        stock = await index.search(vector(1.0, 0.0), VectorFilters(), 50)
        assert f"{prefix}-sold-out" not in [h.handle for h in stock]
        with_sold_out = await index.search(vector(1.0, 0.0), VectorFilters(in_stock_only=False), 50)
        assert f"{prefix}-sold-out" in [h.handle for h in with_sold_out]

        rings = await index.search(vector(1.0, 0.0), VectorFilters(category="ring"), 50)
        assert [h.handle for h in rings if h.handle.startswith(prefix)] == [f"{prefix}-ring"]
    finally:
        async with sessions.begin() as session:
            await session.execute(
                delete(ProductEmbeddingRow).where(ProductEmbeddingRow.handle.like(f"{prefix}-%"))
            )


async def test_upsert_updates_in_place_and_hashes_are_reported(engine: AsyncEngine) -> None:
    prefix = f"it-{uuid.uuid4().hex[:8]}"
    sessions = create_session_factory(engine)
    index = PgVectorIndex(sessions)
    try:
        await index.upsert([product(prefix, "a", vector(1.0), content_hash="v1")])
        await index.upsert([product(prefix, "a", vector(1.0), content_hash="v2", embedding_model="m2")])

        assert (await index.indexed_hashes())[f"{prefix}-a"] == ("v2", "m2")
        await index.delete([f"{prefix}-a"])
        assert f"{prefix}-a" not in await index.indexed_hashes()
    finally:
        async with sessions.begin() as session:
            await session.execute(
                delete(ProductEmbeddingRow).where(ProductEmbeddingRow.handle.like(f"{prefix}-%"))
            )


async def test_the_table_has_an_hnsw_index_with_cosine_ops(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "select indexdef from pg_indexes where indexname = 'ix_product_embeddings_embedding_hnsw'"
                )
            )
        ).scalar_one()

    assert "USING hnsw" in definition
    assert "vector_cosine_ops" in definition
