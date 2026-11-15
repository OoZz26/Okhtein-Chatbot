from app.domain.catalog_overview import render_catalog_overview
from tests.fakes import make_product


def test_one_line_per_category_with_in_stock_count_price_range_and_colours() -> None:
    overview = render_catalog_overview(
        [
            make_product("a", category="Cardholder", color="Khaki", price_min=10000, price_max=10000),
            make_product("b", category="Cardholder", color="Black", price_min=12500, price_max=12500),
            make_product("c", category="Cardholder", color="Gold", available=False),
        ],
        "EGP",
    )

    assert overview == "- Cardholder: 2 in stock, 10,000 to 12,500 EGP; colours: Black, Khaki"


def test_a_category_with_nothing_in_stock_is_marked_sold_out() -> None:
    overview = render_catalog_overview([make_product("w", category="Wallet", available=False)], "EGP")

    assert overview == "- Wallet: sold out right now"


def test_categories_are_sorted_and_a_single_price_is_not_a_range() -> None:
    overview = render_catalog_overview(
        [make_product("r", category="Ring"), make_product("c", category="Clutch")], "EGP"
    )

    assert overview.splitlines() == [
        "- Clutch: 1 in stock, 40,000 EGP; colours: Black",
        "- Ring: 1 in stock, 40,000 EGP; colours: Black",
    ]
