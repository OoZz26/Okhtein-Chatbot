"""ProductRepository adapter that reads the extracted catalog (data/products.json)."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.domain.models import Product

JPEG_QUERY = "format=jpg&width=900"  # Shopify's CDN converts and resizes on request


def _jpeg_url(url: str) -> str:
    if not url:
        return ""
    return f"{url}{'&' if '?' in url else '?'}{JPEG_QUERY}"


class JsonProductRepository:
    def __init__(self, path: Path) -> None:
        raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        self._products = [self._to_product(item) for item in raw]
        self._by_handle = {p.handle: p for p in self._products}

    def get(self, handle: str) -> Product | None:
        return self._by_handle.get(handle)

    def all(self) -> Sequence[Product]:
        return self._products

    @staticmethod
    def _to_product(item: dict[str, Any]) -> Product:
        return Product(
            handle=item["handle"],
            title=item["title"],
            category=item.get("category") or "",
            color=item.get("color") or "",
            price_min=float(item["price_min"]),
            price_max=float(item["price_max"]),
            available=bool(item["available"]),
            tags=tuple(item.get("tags") or ()),
            description=item.get("description") or "",
            image_url=_jpeg_url((item.get("images") or [""])[0]),
        )
