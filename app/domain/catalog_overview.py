"""A short "catalog at a glance" for the agent: what is in stock per category, its price range and colours.

It lets the stylist answer "what's your price range?" or "which colours?" straight away, and know that a
whole category is sold out before promising it.
"""

from collections import defaultdict
from collections.abc import Sequence

from app.domain.models import Product

MAX_COLOURS_LISTED = 8


def render_catalog_overview(products: Sequence[Product], currency: str) -> str:
    by_category: dict[str, list[Product]] = defaultdict(list)
    for product in products:
        if product.category:
            by_category[product.category].append(product)
    lines = [_category_line(name, items, currency) for name, items in sorted(by_category.items())]
    return "\n".join(lines)


def _category_line(name: str, items: Sequence[Product], currency: str) -> str:
    in_stock = [p for p in items if p.available]
    if not in_stock:
        return f"- {name}: sold out right now"
    low = min(p.price_min for p in in_stock)
    high = max(p.price_max for p in in_stock)
    prices = f"{low:,.0f} {currency}" if low == high else f"{low:,.0f} to {high:,.0f} {currency}"
    colours = sorted({p.color for p in in_stock if p.color})
    shown = ", ".join(colours[:MAX_COLOURS_LISTED]) + (
        ", and more" if len(colours) > MAX_COLOURS_LISTED else ""
    )
    return f"- {name}: {len(in_stock)} in stock, {prices}; colours: {shown or 'not listed'}"
