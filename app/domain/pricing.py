"""Price formatting shared by the search tool and the product cards."""

from app.domain.models import Product


def format_price(product: Product, currency: str) -> str:
    """'55,000 EGP', or '40,000 - 60,000 EGP' when the variants differ."""
    if product.price_max != product.price_min:
        return f"{product.price_min:,.0f} - {product.price_max:,.0f} {currency}"
    return f"{product.price_min:,.0f} {currency}"
