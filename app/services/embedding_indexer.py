"""Use case: keep the vector index in step with the catalog, embedding only what changed."""

import logging
from dataclasses import dataclass

from app.domain.models import IndexedProduct, Product
from app.domain.ports import Embedder, ProductRepository, VectorIndex
from app.domain.retrieval.product_text import content_hash, product_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexReport:
    embedded: int
    unchanged: int
    deleted: int


class EmbeddingIndexer:
    def __init__(
        self, products: ProductRepository, embedder: Embedder, index: VectorIndex, embedding_model: str
    ) -> None:
        self._products = products
        self._embedder = embedder
        self._index = index
        self._model = embedding_model

    async def run(self) -> IndexReport:
        """Embed new and changed products (or all of them when the model changed), delete removed ones."""
        indexed = await self._index.indexed_hashes()
        catalog = {p.handle: p for p in self._products.all()}
        texts = {handle: product_text(p) for handle, p in catalog.items()}
        stale = [
            handle
            for handle, text in texts.items()
            if indexed.get(handle) != (content_hash(text), self._model)  # new, changed text, or other model
        ]
        removed = [handle for handle in indexed if handle not in catalog]
        if stale:
            vectors = await self._embedder.embed([texts[h] for h in stale])
            await self._index.upsert(
                [self._item(catalog[h], texts[h], vector) for h, vector in zip(stale, vectors, strict=True)]
            )
        await self._index.delete(removed)
        report = IndexReport(len(stale), len(catalog) - len(stale), len(removed))
        logger.info(
            "embedding_index embedded=%d unchanged=%d deleted=%d",
            report.embedded,
            report.unchanged,
            report.deleted,
        )
        return report

    def _item(self, product: Product, text: str, vector: list[float]) -> IndexedProduct:
        return IndexedProduct(
            handle=product.handle,
            content_hash=content_hash(text),
            embedding_model=self._model,
            category=product.category,
            price_min=product.price_min,
            available=product.available,
            title=product.title,
            embedding=tuple(vector),
        )
