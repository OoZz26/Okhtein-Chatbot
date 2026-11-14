"""Compare the retrieval strategies on ~25 labelled queries: hit@3 for keyword, vector and hybrid.

Usage: python scripts/eval_retrieval.py   (needs the index: python scripts/build_embeddings.py)
Query embeddings are cached in tests/evals/reports/ so re-running costs nothing.
"""

import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from app.bootstrap import build_embedder
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.ports import Embedder
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.retrieval.retrievers import HybridRetriever, KeywordRetriever, VectorRetriever
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.db.pgvector_index import PgVectorIndex
from app.infra.db.session import create_engine, create_session_factory
from tests.evals.retrieval_eval import DEFAULT_K, evaluate, load_cases, render

CACHE_PATH = Path(__file__).parent.parent / "tests" / "evals" / "reports" / "query_embeddings.json"


class CachingEmbedder:
    """Remembers query embeddings on disk, so repeated eval runs do not pay for them again."""

    def __init__(self, inner: Embedder, model: str) -> None:
        self._inner = inner
        self._key = model
        CACHE_PATH.parent.mkdir(exist_ok=True)
        self._cache: dict[str, list[float]] = (
            json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        missing = [t for t in texts if f"{self._key}|{t}" not in self._cache]
        if missing:
            for text, vector in zip(missing, await self._inner.embed(missing), strict=True):
                self._cache[f"{self._key}|{text}"] = vector
            CACHE_PATH.write_text(json.dumps(self._cache), encoding="utf-8")
        return [self._cache[f"{self._key}|{t}"] for t in texts]


async def main() -> int:
    settings = get_settings()
    engine = create_engine(
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_user,
        settings.postgres_password,
        settings.postgres_db,
    )
    products = JsonProductRepository(Path(settings.products_path))
    keyword = KeywordSearch(products)
    embedder = CachingEmbedder(build_embedder(settings), settings.embedding_model)
    index = PgVectorIndex(create_session_factory(engine))
    cases = load_cases()
    try:
        results = [
            await evaluate("keyword", KeywordRetriever(keyword), cases),
            await evaluate("vector", VectorRetriever(embedder, index, products), cases),
            await evaluate("hybrid", HybridRetriever(embedder, index, products, keyword), cases),
        ]
    finally:
        await engine.dispose()
    print(f"{len(cases)} labelled queries\n")
    print(render(results))
    for result in results:
        print(f"\n{result.name} missed: {', '.join(result.misses) or '(nothing)'}")
    keyword_rate, hybrid_rate = results[0].hit_rate, results[2].hit_rate
    ok = hybrid_rate >= 0.8 and hybrid_rate >= keyword_rate
    verdict = "✅" if ok else "❌"
    summary = f"hybrid {hybrid_rate:.0%} vs keyword {keyword_rate:.0%} at k={DEFAULT_K}"
    print(f"\n{verdict} {summary} (target: hybrid >= 80% and >= keyword)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    configure_logging(logging.WARNING)
    sys.exit(asyncio.run(main()))
