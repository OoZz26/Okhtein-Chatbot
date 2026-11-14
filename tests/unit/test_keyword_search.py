from app.domain.retrieval.keyword import KeywordSearch, SearchQuery
from tests.fakes import InMemoryProducts, make_product

CATALOG = InMemoryProducts(
    [
        make_product("black-clutch", price_min=40000, price_max=40000),
        make_product("gold-clutch", title="Gold Clutch", color="Gold", price_min=90000, price_max=90000),
        make_product("sold-out-clutch", title="Sold Out Clutch", available=False),
        make_product("silver-ring", title="Silver Ring", category="Ring", color="Silver", price_min=9000),
    ]
)
SEARCH = KeywordSearch(CATALOG)


def handles(query: SearchQuery) -> list[str]:
    return [p.handle for p in SEARCH.search(query)]


def test_best_keyword_match_is_ranked_first() -> None:
    assert handles(SearchQuery("black clutch"))[0] == "black-clutch"


def test_out_of_stock_hidden_unless_requested() -> None:
    assert "sold-out-clutch" not in handles(SearchQuery(category="Clutch"))
    assert "sold-out-clutch" in handles(SearchQuery(category="Clutch", include_out_of_stock=True))


def test_budget_is_respected() -> None:
    assert handles(SearchQuery(category="Clutch", max_price=50000)) == ["black-clutch"]


def test_category_filter_is_case_insensitive() -> None:
    assert handles(SearchQuery(category="ring")) == ["silver-ring"]


def test_unmatched_keywords_return_nothing() -> None:
    assert handles(SearchQuery("purple unicorn")) == []


def test_plural_keywords_match() -> None:
    assert handles(SearchQuery("rings")) == ["silver-ring"]


def test_categories_are_listed() -> None:
    assert SEARCH.categories() == ["Clutch", "Ring"]
