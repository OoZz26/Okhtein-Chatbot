"""Retrieval evaluation: labelled queries, scored as hit@k per strategy.

A case is a query plus an `expect` label. The label says what a good result looks like:
`category_any` (category contains one of these), `text_any` (title/colour/description contains one of
these words) and `max_price`. A query is a HIT when at least one of the top-k products satisfies ALL the
criteria of its label.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.errors import RetrievalError
from app.domain.models import Product
from app.domain.retrieval.base import Retriever
from app.domain.retrieval.keyword import SearchQuery

CASES_PATH = Path(__file__).parent / "retrieval_cases.json"
DEFAULT_K = 3


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    expect: dict[str, Any]
    max_price: float | None = None


@dataclass
class StrategyResult:
    name: str
    hits: list[bool] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return sum(self.hits) / len(self.hits) if self.hits else 0.0


def load_cases(path: Path = CASES_PATH) -> list[RetrievalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [RetrievalCase(item["query"], item["expect"], item.get("max_price")) for item in raw]


def satisfies(product: Product, expect: dict[str, Any]) -> bool:
    text = " ".join([product.title, product.color, product.category, product.description]).lower()
    category_ok = any(c.lower() in product.category.lower() for c in expect.get("category_any", [])) or (
        "category_any" not in expect
    )
    text_ok = any(w.lower() in text for w in expect.get("text_any", [])) or "text_any" not in expect
    price_ok = "max_price" not in expect or product.price_min <= expect["max_price"]
    return category_ok and text_ok and price_ok


def is_hit(top: Sequence[Product], expect: dict[str, Any]) -> bool:
    return any(satisfies(product, expect) for product in top)


async def evaluate(
    name: str, retriever: Retriever, cases: Sequence[RetrievalCase], k: int = DEFAULT_K
) -> StrategyResult:
    result = StrategyResult(name)
    for case in cases:
        try:
            groups = await retriever.search(SearchQuery(case.query, max_price=case.max_price, limit=k))
        except RetrievalError:
            groups = []  # a strategy that cannot answer scores a miss; it is not rescued by a fallback here
        hit = is_hit([g.product for g in groups[:k]], case.expect)
        result.hits.append(hit)
        if not hit:
            result.misses.append(case.query)
    return result


def render(results: Sequence[StrategyResult], k: int = DEFAULT_K) -> str:
    lines = [f"{'strategy':<10}{f'hit@{k}':<9}misses"]
    for r in results:
        lines.append(f"{r.name:<10}{r.hit_rate:<9.0%}{len(r.misses)} of {len(r.hits)}")
    return "\n".join(lines)
