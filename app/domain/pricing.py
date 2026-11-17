"""Price formatting shared by the search tool and the product cards."""

from app.domain.models import Product


def format_price(product: Product, currency: str) -> str:
    """'55,000 EGP', or '40,000 to 60,000 EGP' when the variants differ.
    Written with 'to', not a dash: the model copies what it reads, and replies must not have dashes."""
    if product.price_max != product.price_min:
        return f"{product.price_min:,.0f} to {product.price_max:,.0f} {currency}"
    return f"{product.price_min:,.0f} {currency}"
