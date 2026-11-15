from app.domain.retrieval.keyword import KeywordSearch
from app.domain.retrieval.retrievers import KeywordRetriever
from app.domain.tools.search_products import SearchProductsTool
from tests.fakes import InMemoryProducts, make_product

PRODUCTS = InMemoryProducts(
    [
        make_product("lotus-black", title="Lotus Clutch", color="Black"),
        make_product("lotus-gold", title="Lotus Clutch", color="Gold"),
        make_product("bond-ring", title="Bond Ring", category="Ring", color="Gold"),
    ]
)


def tool() -> SearchProductsTool:
    search = KeywordSearch(PRODUCTS)
    return SearchProductsTool(KeywordRetriever(search), search.categories(), "EGP", 5)


async def test_colour_variants_are_listed_once_with_the_other_colours() -> None:
    result = await tool().run({"query": "lotus clutch"})

    assert [r["handle"] for r in result["results"]] == ["lotus-black"]
    assert result["results"][0]["other_colours"] == ["Gold"]


async def test_a_real_category_filters_the_search() -> None:
    result = await tool().run({"query": "gold", "category": "ring"})

    assert [r["handle"] for r in result["results"]] == ["bond-ring"]
    assert "note" not in result


async def test_an_invented_category_is_ignored_with_a_helpful_note() -> None:
    result = await tool().run({"query": "gold ring", "category": "wedding"})

    assert result["results"]  # the search still works, without the bogus filter
    assert "not a catalog category" in result["note"]
    assert "Clutch" in result["note"]  # and the model is told what is valid


async def test_results_never_contain_urls() -> None:
    result = await tool().run({"query": "gold"})

    assert "http" not in str(result)


SMALL_LEATHER = InMemoryProducts(
    [
        make_product("envelope-wallet", title="Envelope Wallet", category="Wallet", available=False),
        make_product("palmette-cardholder", title="Palmette Cardholder", category="Cardholder"),
    ]
)


def small_leather_tool() -> SearchProductsTool:
    search = KeywordSearch(SMALL_LEATHER)
    return SearchProductsTool(KeywordRetriever(search), search.categories(), "EGP", 5)


async def test_a_sold_out_category_returns_the_closest_in_stock_pieces_and_says_why() -> None:
    result = await small_leather_tool().run({"query": "black leather", "category": "wallet"})

    assert [r["handle"] for r in result["results"]] == ["palmette-cardholder"]
    assert "No in-stock wallet is sold out right now" in result["note"]
    assert "Never just say you could not find anything" in result["note"]


async def test_an_in_stock_category_gets_no_fallback_note() -> None:
    result = await small_leather_tool().run({"query": "black", "category": "cardholder"})

    assert [r["handle"] for r in result["results"]] == ["palmette-cardholder"]
    assert "note" not in result


async def test_asking_for_sold_out_pieces_on_purpose_does_not_fall_back() -> None:
    result = await small_leather_tool().run(
        {"query": "black", "category": "wallet", "include_out_of_stock": True}
    )

    assert [r["handle"] for r in result["results"]] == ["envelope-wallet"]
    assert "note" not in result
