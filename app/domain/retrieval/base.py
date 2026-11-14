"""The Retriever strategy: every way of finding products for a query has this one method."""

from typing import Protocol

from app.domain.models import ProductGroup
from app.domain.retrieval.keyword import SearchQuery


class Retriever(Protocol):
    async def search(self, query: SearchQuery) -> list[ProductGroup]: ...
