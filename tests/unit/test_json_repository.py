from pathlib import Path

from app.infra.catalog.json_repository import JsonProductRepository

PRODUCTS_JSON = Path(__file__).parents[2] / "data" / "products.json"


def test_loads_the_real_catalog() -> None:
    repo = JsonProductRepository(PRODUCTS_JSON)
    assert len(repo.all()) == 212
    first = repo.all()[0]
    assert repo.get(first.handle) == first
    assert repo.get("does-not-exist") is None


def test_product_images_are_requested_as_resized_jpegs() -> None:
    product = JsonProductRepository(PRODUCTS_JSON).all()[0]

    assert product.image_url.startswith("https://cdn.shopify.com/")
    assert "format=jpg" in product.image_url
    assert "width=900" in product.image_url
