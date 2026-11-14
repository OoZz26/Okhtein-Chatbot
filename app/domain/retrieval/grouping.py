"""Collapsing colour variants of the same model, so three copies of one bag do not fill the results."""

from collections.abc import Sequence

from app.domain.models import Product, ProductGroup


def group_variants(products: Sequence[Product]) -> list[ProductGroup]:
    """Keep the first (best-ranked) product of each title and list the colours of the others.

    The input order is the ranking, and it is preserved.
    """
    groups: dict[str, list[Product]] = {}
    for product in products:
        groups.setdefault(product.title.strip().lower(), []).append(product)
    result = []
    for members in groups.values():
        best = members[0]
        others = tuple(m.color for m in members[1:] if m.color and m.color != best.color)
        result.append(ProductGroup(best, others))
    return result
