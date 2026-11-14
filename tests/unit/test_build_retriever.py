"""The retrieval strategy is chosen by RETRIEVER in the settings: no code change."""

import pytest

from app.bootstrap import build_retriever
from app.core.config import Settings
from app.domain.errors import ConfigurationError
from app.domain.retrieval.keyword import KeywordSearch
from app.domain.retrieval.retrievers import FallbackRetriever, KeywordRetriever
from tests.fakes import InMemoryProducts, make_product

KEYWORD = KeywordSearch(InMemoryProducts([make_product("black-clutch")]))


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"openai_api_key": "sk-test", "_env_file": None}
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_keyword_is_plain_keyword_search() -> None:
    assert isinstance(build_retriever(settings(retriever="keyword"), KEYWORD), KeywordRetriever)


@pytest.mark.parametrize("strategy", ["vector", "hybrid"])
def test_semantic_strategies_are_wrapped_with_a_keyword_fallback(strategy: str) -> None:
    assert isinstance(build_retriever(settings(retriever=strategy), KEYWORD), FallbackRetriever)


def test_hybrid_is_the_default() -> None:
    assert settings().retriever == "hybrid"


def test_without_an_openai_key_semantic_search_degrades_to_keyword() -> None:
    retriever = build_retriever(settings(retriever="hybrid", openai_api_key=""), KEYWORD)

    assert isinstance(retriever, KeywordRetriever)


def test_an_unknown_strategy_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        build_retriever(settings(retriever="magic"), KEYWORD)
