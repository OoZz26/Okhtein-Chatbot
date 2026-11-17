from app.domain.pricing import format_price
from app.domain.product_links import product_url
from tests.fakes import make_product


def test_a_single_price() -> None:
    assert format_price(make_product(), "EGP") == "40,000 EGP"


def test_a_price_range_uses_to_not_a_dash() -> None:
    product = make_product(price_min=40000.0, price_max=60000.0)
    assert format_price(product, "EGP") == "40,000 to 60,000 EGP"


def test_product_url_is_built_from_the_handle() -> None:
    assert product_url("https://eg.okhtein.com/", "black-clutch") == (
        "https://eg.okhtein.com/products/black-clutch"
    )
