"""The `search_products` tool. Results never include URLs: our code builds links from handles."""

from typing import Any

from app.domain.models import Product
from app.domain.retrieval.keyword import KeywordSearch, SearchQuery


class SearchProductsTool:
    name = "search_products"

    def __init__(self, search: KeywordSearch, currency: str, result_limit: int) -> None:
        self._search = search
        self._currency = currency
        self._result_limit = result_limit
        categories = ", ".join(search.categories())
        self.description = (
            "Search the Okhtein catalog. Returns products with handle, title, colour, price and stock. "
            "Use English keywords. Only in-stock products are returned unless include_out_of_stock is true."
        )
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "English keywords such as colour, material, style or occasion.",
                },
                "category": {"type": "string", "description": f"Optional category. One of: {categories}."},
                "max_price": {"type": "number", "description": f"Optional budget ceiling in {currency}."},
                "include_out_of_stock": {"type": "boolean", "description": "Include sold-out products."},
            },
            "required": ["query"],
        }

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        max_price = arguments.get("max_price")
        query = SearchQuery(
            text=str(arguments.get("query") or ""),
            category=str(arguments["category"]) if arguments.get("category") else None,
            max_price=float(max_price) if max_price is not None else None,
            include_out_of_stock=bool(arguments.get("include_out_of_stock", False)),
            limit=self._result_limit,
        )
        return {"results": [self._describe(p) for p in self._search.search(query)]}

    def _describe(self, product: Product) -> dict[str, Any]:
        return {
            "handle": product.handle,
            "title": product.title,
            "category": product.category,
            "color": product.color,
            "price": self._format_price(product),
            "in_stock": product.available,
        }

    def _format_price(self, product: Product) -> str:
        if product.price_max != product.price_min:
            return f"{product.price_min:,.0f} - {product.price_max:,.0f} {self._currency}"
        return f"{product.price_min:,.0f} {self._currency}"
