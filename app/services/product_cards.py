"""Builds the picture-and-caption cards for the products the agent recommended."""

from app.domain.models import ProductCard
from app.domain.ports import ProductRepository
from app.domain.pricing import format_price


class ProductCardFactory:
    def __init__(self, products: ProductRepository, store_url: str, currency: str) -> None:
        self._products = products
        self._store_url = store_url.rstrip("/")
        self._currency = currency

    def build(self, handles: list[str]) -> list[ProductCard]:
        cards = []
        for handle in handles:
            product = self._products.get(handle)
            if product is not None:
                link = f"{self._store_url}/products/{handle}"
                cards.append(
                    ProductCard(product.title, format_price(product, self._currency), link, product.image_url)
                )
        return cards
