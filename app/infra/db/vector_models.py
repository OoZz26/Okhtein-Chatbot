"""pgvector table: one embedding per product, with the filterable facts stored next to it."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small


class VectorBase(DeclarativeBase):
    """Separate from the main metadata: this table needs the `vector` extension, which may be missing."""


class ProductEmbeddingRow(VectorBase):
    __tablename__ = "product_embeddings"
    # HNSW = an approximate nearest-neighbour graph index. Brute force compares the query with every
    # row (exact, O(n)); HNSW walks a layered graph toward the nearest ones (fast, slightly approximate).
    __table_args__ = (
        Index(
            "ix_product_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    handle: Mapped[str] = mapped_column(String(255), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(128), default="")
    price_min: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column()
    title: Mapped[str] = mapped_column(String(512))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
