"""The `search_products` tool. Results never include URLs: our code builds links from handles."""

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.domain.models import ProductGroup
from app.domain.pricing import format_price
from app.domain.retrieval.base import Retriever
from app.domain.retrieval.keyword import SearchQuery


class SearchProductsTool:
    name = "search_products"

    def __init__(
        self, retriever: Retriever, categories: Sequence[str], currency: str, result_limit: int
    ) -> None:
        self._retriever = retriever
        self._categories = list(categories)
        self._currency = currency
        self._result_limit = result_limit
        self.description = (
            "Search the Okhtein catalog. Returns products with handle, title, colour, price and stock; "
            "colour variants of the same model are listed once with `other_colours`. "
            "Describe what the customer wants in English (style, occasion, colour, material, recipient). "
            "Only in-stock products are returned unless include_out_of_stock is true."
        )
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "English description: colour, material, style, occasion, who it is for.",
                },
                "category": {
                    "type": "string",
                    "description": f"Optional category. One of: {', '.join(categories)}.",
                },
                "max_price": {"type": "number", "description": f"Optional budget ceiling in {currency}."},
                "include_out_of_stock": {"type": "boolean", "description": "Include sold-out products."},
            },
            "required": ["query"],
        }

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        max_price = arguments.get("max_price")
        category, note = self._known_category(arguments.get("category"))
        query = SearchQuery(
            text=str(arguments.get("query") or ""),
            category=category,
            max_price=float(max_price) if max_price is not None else None,
            include_out_of_stock=bool(arguments.get("include_out_of_stock", False)),
            limit=self._result_limit,
        )
        groups = await self._retriever.search(query)
        if not groups and category and not query.include_out_of_stock:
            groups, note = await self._closest_in_stock(query, category)
        result: dict[str, Any] = {"results": [self._describe(group) for group in groups]}
        if note:
            result["note"] = note
        return result

    async def _closest_in_stock(self, query: SearchQuery, category: str) -> tuple[list[ProductGroup], str]:
        """Nothing of this category is in stock: never leave the customer with "I couldn't find
        anything". Say why, and return the closest in-stock pieces from other categories instead."""
        sold_out = await self._retriever.search(replace(query, include_out_of_stock=True))
        alternatives = await self._retriever.search(
            replace(query, text=f"{query.text} {category}".strip(), category=None)
        )
        why = "is sold out right now" if sold_out else "matches this search right now"
        return alternatives, (
            f"No in-stock {category} {why}. The results below are the closest in-stock pieces from other "
            "categories. Tell the customer honestly in one kind line, then offer the closest similar "
            "alternative (check the catalog at a glance for a related category and search it if these are "
            "not similar enough). Never just say you could not find anything."
        )

    def _known_category(self, requested: object) -> tuple[str | None, str]:
        """Only real catalog categories filter the search; an invented one (like 'wedding') is ignored."""
        if not requested:
            return None, ""
        wanted = str(requested).strip().lower()
        if any(wanted in known.lower() or known.lower() in wanted for known in self._categories):
            return str(requested).strip(), ""
        valid = ", ".join(self._categories)
        return None, f"'{requested}' is not a catalog category, so it was ignored. Valid categories: {valid}."

    def _describe(self, group: ProductGroup) -> dict[str, Any]:
        product = group.product
        described: dict[str, Any] = {
            "handle": product.handle,
            "title": product.title,
            "category": product.category,
            "color": product.color,
            "price": format_price(product, self._currency),
            "in_stock": product.available,
        }
        if group.other_colours:
            described["other_colours"] = list(group.other_colours)
        return described
