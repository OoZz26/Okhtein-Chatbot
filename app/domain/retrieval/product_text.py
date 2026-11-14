"""The text we embed for each product, and the hash that tells us when it changed."""

import hashlib

from app.domain.models import Product


def product_text(product: Product) -> str:
    """A rich description of the product: what a customer might search for, in one paragraph."""
    parts = [
        product.title,
        f"Category: {product.category}" if product.category else "",
        f"Colour: {product.color}" if product.color else "",
        f"Tags: {', '.join(product.tags)}" if product.tags else "",
        product.description,
    ]
    return ". ".join(part.strip() for part in parts if part.strip())


def content_hash(text: str) -> str:
    """Stable fingerprint: re-embed a product only when this changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
