"""The retrieval strategies: keyword, vector, hybrid, and a fallback that chains two of them."""

import logging
from dataclasses import replace

from app.domain.errors import RetrievalError
from app.domain.models import Product, ProductGroup, VectorFilters
from app.domain.ports import Embedder, ProductRepository, VectorIndex
from app.domain.retrieval.base import Retriever
from app.domain.retrieval.grouping import group_variants
from app.domain.retrieval.keyword import KeywordSearch, SearchQuery, tokenize

logger = logging.getLogger(__name__)

CANDIDATE_MULTIPLIER = 4  # fetch more than we show: grouping variants removes some, boosts reorder others
NAME_MATCH_BOOST = 0.10  # a query word in the product's title is a strong signal
COLOUR_MATCH_BOOST = 0.05


def _filters(query: SearchQuery) -> VectorFilters:
    return VectorFilters(query.category, query.max_price, in_stock_only=not query.include_out_of_stock)


class KeywordRetriever:
    """The original word-matching search, behind the Retriever interface."""

    def __init__(self, search: KeywordSearch) -> None:
        self._search = search

    async def search(self, query: SearchQuery) -> list[ProductGroup]:
        wide = replace(query, limit=query.limit * CANDIDATE_MULTIPLIER)
        return group_variants(self._search.search(wide))[: query.limit]


class _VectorBacked:
    """Shared plumbing for strategies that rank by embedding similarity."""

    def __init__(self, embedder: Embedder, index: VectorIndex, products: ProductRepository) -> None:
        self._embedder = embedder
        self._index = index
        self._products = products

    async def _similar(self, query: SearchQuery) -> list[tuple[Product, float]]:
        [vector] = await self._embedder.embed([query.text])
        hits = await self._index.search(vector, _filters(query), query.limit * CANDIDATE_MULTIPLIER)
        if not hits and not await self._index.search(vector, VectorFilters(in_stock_only=False), 1):
            # Nothing even without filters: the index itself is empty. (Filters matching nothing is a
            # legitimate empty answer, not a failure.)
            raise RetrievalError("The vector index is empty (is it built? run build_embeddings.py)")
        found = [(self._products.get(h.handle), h.score) for h in hits]
        return [(product, score) for product, score in found if product is not None]


class VectorRetriever(_VectorBacked):
    """Pure semantic search: filters and similarity in one query, no keyword influence."""

    async def search(self, query: SearchQuery) -> list[ProductGroup]:
        ranked = await self._similar(query)
        return group_variants([product for product, _ in ranked])[: query.limit]


class HybridRetriever(_VectorBacked):
    """Semantic ranking with hard filters, plus a boost when the query names the product or its colour."""

    def __init__(
        self, embedder: Embedder, index: VectorIndex, products: ProductRepository, keyword: KeywordSearch
    ) -> None:
        super().__init__(embedder, index, products)
        self._keyword = keyword

    async def search(self, query: SearchQuery) -> list[ProductGroup]:
        if not query.text.strip():  # nothing to embed: "browse this category" is a keyword job
            return await KeywordRetriever(self._keyword).search(query)
        ranked = await self._similar(query)
        words = tokenize(query.text)
        boosted = sorted(ranked, key=lambda pair: pair[1] + self._boost(pair[0], words), reverse=True)
        return group_variants([product for product, _ in boosted])[: query.limit]

    @staticmethod
    def _boost(product: Product, words: set[str]) -> float:
        boost = NAME_MATCH_BOOST if words & tokenize(product.title) else 0.0
        return boost + (COLOUR_MATCH_BOOST if words & tokenize(product.color) else 0.0)


class FallbackRetriever:
    """Tries the smart strategy; if it is unavailable, answers with the simple one and logs why."""

    def __init__(self, primary: Retriever, fallback: Retriever) -> None:
        self._primary = primary
        self._fallback = fallback

    async def search(self, query: SearchQuery) -> list[ProductGroup]:
        try:
            return await self._primary.search(query)
        except RetrievalError as exc:
            logger.warning("retrieval_fallback strategy=keyword reason=%s", exc)
            return await self._fallback.search(query)
