from app.domain.retrieval.retrievers import KeywordRetriever
from tests.evals.retrieval_eval import RetrievalCase, evaluate, is_hit, load_cases, render, satisfies
from tests.fakes import InMemoryProducts, make_product

RING = make_product("ring", title="Bond Ring", category="Ring", color="Gold", price_min=85000)
CLUTCH = make_product("clutch", title="Lotus Clutch", category="Clutch", color="Black", price_min=40000)


def test_a_product_must_satisfy_every_criterion_of_the_label() -> None:
    label = {"category_any": ["Ring"], "text_any": ["gold"], "max_price": 90000}

    assert satisfies(RING, label)
    assert not satisfies(RING, {**label, "max_price": 50000})  # too expensive
    assert not satisfies(CLUTCH, label)  # wrong category
    assert not satisfies(RING, {"category_any": ["Ring"], "text_any": ["silver"]})


def test_a_query_is_a_hit_when_any_top_result_satisfies_the_label() -> None:
    assert is_hit([CLUTCH, RING], {"category_any": ["Ring"]})
    assert not is_hit([CLUTCH], {"category_any": ["Ring"]})
    assert not is_hit([], {"category_any": ["Ring"]})


async def test_evaluate_reports_hit_rate_and_misses() -> None:
    from app.domain.retrieval.keyword import KeywordSearch

    retriever = KeywordRetriever(KeywordSearch(InMemoryProducts([RING, CLUTCH])))
    cases = [
        RetrievalCase("gold ring", {"category_any": ["Ring"]}),
        RetrievalCase("something unfindable", {"category_any": ["Ring"]}),
    ]

    result = await evaluate("keyword", retriever, cases)

    assert result.hit_rate == 0.5
    assert result.misses == ["something unfindable"]
    assert "keyword" in render([result]) and "50%" in render([result])


def test_the_shipped_cases_load_and_cover_arabic_and_budgets() -> None:
    cases = load_cases()

    assert len(cases) >= 25
    assert any(any("؀" <= ch <= "ۿ" for ch in case.query) for case in cases)  # Arabic queries
    assert any(case.max_price for case in cases)  # budget queries
