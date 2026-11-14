"""Plain keyword + filter search. Smarter (hybrid/semantic) retrieval comes in a later slice."""

import re
from dataclasses import dataclass

from app.domain.models import Product
from app.domain.ports import ProductRepository

_STOP_WORDS = frozenset(
    {"the", "a", "an", "for", "and", "or", "with", "of", "in", "to", "my", "me", "i", "want", "need"}
    | {"something", "some", "any", "please", "show", "looking", "under", "below", "egp"}
)
_STRONG_FIELD_WEIGHT = 3  # a hit in title/colour/category/tags counts more than one in the description
_WEAK_FIELD_WEIGHT = 1
_MIN_PLURAL_LENGTH = 4  # "rings" -> "ring", but leave "bus" alone


@dataclass(frozen=True)
class SearchQuery:
    text: str = ""
    category: str | None = None
    max_price: float | None = None
    include_out_of_stock: bool = False
    limit: int = 5


def tokenize(text: str) -> set[str]:
    tokens = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in _STOP_WORDS:
            continue
        if len(word) >= _MIN_PLURAL_LENGTH and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.add(word)
    return tokens


class KeywordSearch:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def categories(self) -> list[str]:
        return sorted({p.category for p in self._products.all() if p.category})

    def search(self, query: SearchQuery) -> list[Product]:
        candidates = [p for p in self._products.all() if self._passes_filters(p, query)]
        words = tokenize(query.text)
        if not words:
            return sorted(candidates, key=lambda p: p.price_min)[: query.limit]
        scored = [(self._score(p, words), p) for p in candidates]
        matches = [(score, p) for score, p in scored if score > 0]
        matches.sort(key=lambda pair: (-pair[0], pair[1].price_min))
        return [p for _, p in matches[: query.limit]]

    @staticmethod
    def _passes_filters(product: Product, query: SearchQuery) -> bool:
        if not product.available and not query.include_out_of_stock:
            return False
        if query.max_price is not None and product.price_min > query.max_price:
            return False
        return not (query.category and query.category.lower() not in product.category.lower())

    @staticmethod
    def _score(product: Product, words: set[str]) -> int:
        strong = tokenize(" ".join([product.title, product.color, product.category, *product.tags]))
        weak = tokenize(product.description)
        return sum(
            _STRONG_FIELD_WEIGHT if w in strong else _WEAK_FIELD_WEIGHT if w in weak else 0 for w in words
        )
