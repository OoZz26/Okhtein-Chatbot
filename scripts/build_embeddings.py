"""Embed the catalog into the pgvector index. Safe to re-run: unchanged products are skipped.

Usage: python scripts/build_embeddings.py
"""

import asyncio
import logging
import sys
from pathlib import Path

from app.bootstrap import build_embedder
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.db.pgvector_index import PgVectorIndex, ensure_vector_support
from app.infra.db.session import create_engine, create_session_factory
from app.services.embedding_indexer import EmbeddingIndexer


async def main() -> int:
    settings = get_settings()
    if not settings.openai_api_key:
        print("❌ OPENAI_API_KEY is not set in .env: embeddings need it.")
        return 1
    engine = create_engine(
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_user,
        settings.postgres_password,
        settings.postgres_db,
    )
    try:
        if not await ensure_vector_support(engine):
            print("❌ pgvector is not available: use the pgvector image from docker-compose.yml.")
            return 1
        indexer = EmbeddingIndexer(
            JsonProductRepository(Path(settings.products_path)),
            build_embedder(settings),
            PgVectorIndex(create_session_factory(engine)),
            settings.embedding_model,
        )
        report = await indexer.run()
    finally:
        await engine.dispose()
    print(
        f"✅ embedded {report.embedded}, unchanged {report.unchanged}, deleted {report.deleted} "
        f"(model {settings.embedding_model})"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    configure_logging(logging.WARNING)
    sys.exit(asyncio.run(main()))
