import pytest

from app.domain.errors import RetrievalError
from app.domain.models import Product, ProductGroup
from app.domain.retrieval.grouping import group_variants
from app.domain.retrieval.keyword import KeywordSearch, SearchQuery
from app.domain.retrieval.product_text import content_hash, product_text
from app.domain.retrieval.retrievers import (
    FallbackRetriever,
    HybridRetriever,
    KeywordRetriever,
    VectorRetriever,
)
from app.services.embedding_indexer import EmbeddingIndexer
from tests.fakes import FakeEmbedder, InMemoryProducts, InMemoryVectorIndex, make_product

CATALOG = [
    make_product(
        "lotus-black",
        title="Lotus Clutch",
        color="Black",
        price_min=65000,
        price_max=65000,
        description="Sculpted evening clutch with lotus motif",
    ),
    make_product(
        "lotus-gold",
        title="Lotus Clutch",
        color="Gold",
        price_min=65000,
        price_max=65000,
        description="Sculpted evening clutch with lotus motif",
    ),
    make_product(
        "bond-ring",
        title="Bond Ring",
        category="Ring",
        color="Gold",
        price_min=85000,
        price_max=85000,
        description="Bold interlocking gold ring for celebrations",
    ),
    make_product(
        "o-cardholder",
        title="O Charm Cardholder",
        category="Cardholder",
        color="Black",
        price_min=11000,
        price_max=11000,
        description="Small everyday cardholder",
    ),
    make_product(
        "sold-out-bag",
        title="Sold Out Bag",
        category="Top Handle Bag",
        available=False,
        description="Bold evening bag",
    ),
]
PRODUCTS = InMemoryProducts(CATALOG)
KEYWORD = KeywordSearch(PRODUCTS)


async def indexed() -> tuple[FakeEmbedder, InMemoryVectorIndex]:
    embedder, index = FakeEmbedder(), InMemoryVectorIndex()
    await EmbeddingIndexer(PRODUCTS, embedder, index, "fake-model").run()
    embedder.embedded_texts.clear()
    return embedder, index


def handles(groups: list[ProductGroup]) -> list[str]:
    return [group.product.handle for group in groups]


class TestGrouping:
    def test_colour_variants_collapse_into_one_result_listing_the_other_colours(self) -> None:
        groups = group_variants([CATALOG[0], CATALOG[2], CATALOG[1]])

        assert [g.product.handle for g in groups] == ["lotus-black", "bond-ring"]  # ranking order kept
        assert groups[0].other_colours == ("Gold",)
        assert groups[1].other_colours == ()

    def test_different_models_are_never_merged(self) -> None:
        assert len(group_variants([CATALOG[2], CATALOG[3]])) == 2


class TestProductText:
    def test_the_text_mentions_what_a_customer_might_search_for(self) -> None:
        text = product_text(CATALOG[0])

        assert "Lotus Clutch" in text
        assert "Category: Clutch" in text
        assert "Colour: Black" in text
        assert "lotus motif" in text

    def test_the_hash_changes_when_the_text_changes(self) -> None:
        assert content_hash("a") == content_hash("a")
        assert content_hash("a") != content_hash("b")


class TestKeywordRetriever:
    async def test_variants_are_grouped_in_keyword_results_too(self) -> None:
        groups = await KeywordRetriever(KEYWORD).search(SearchQuery("lotus clutch"))

        assert handles(groups) == ["lotus-black"]
        assert groups[0].other_colours == ("Gold",)


class TestVectorAndHybrid:
    async def test_vector_retrieval_ranks_by_similarity(self) -> None:
        embedder, index = await indexed()

        groups = await VectorRetriever(embedder, index, PRODUCTS).search(
            SearchQuery("bold interlocking gold ring for celebrations", limit=3)
        )

        assert handles(groups)[0] == "bond-ring"

    async def test_filters_are_applied_in_the_same_search_as_the_ranking(self) -> None:
        embedder, index = await indexed()
        retriever = HybridRetriever(embedder, index, PRODUCTS, KEYWORD)

        under_budget = await retriever.search(SearchQuery("bold evening gold", max_price=70000))
        in_category = await retriever.search(SearchQuery("bold evening gold", category="Ring"))
        with_sold_out = await retriever.search(
            SearchQuery("bold evening bag", include_out_of_stock=True, limit=5)
        )
        without_sold_out = await retriever.search(SearchQuery("bold evening bag", limit=5))

        assert "bond-ring" not in handles(under_budget)  # 85,000 is over budget
        assert handles(in_category) == ["bond-ring"]
        assert "sold-out-bag" in handles(with_sold_out)
        assert "sold-out-bag" not in handles(without_sold_out)

    async def test_the_hybrid_boost_prefers_a_product_named_in_the_query(self) -> None:
        embedder, index = await indexed()

        groups = await HybridRetriever(embedder, index, PRODUCTS, KEYWORD).search(
            SearchQuery("cardholder", limit=5)
        )

        assert handles(groups)[0] == "o-cardholder"

    async def test_hybrid_groups_colour_variants(self) -> None:
        embedder, index = await indexed()

        groups = await HybridRetriever(embedder, index, PRODUCTS, KEYWORD).search(
            SearchQuery("sculpted evening clutch lotus", limit=5)
        )

        assert handles(groups).count("lotus-black") + handles(groups).count("lotus-gold") == 1

    async def test_an_empty_query_is_a_keyword_browse_not_an_embedding_call(self) -> None:
        embedder, index = await indexed()

        groups = await HybridRetriever(embedder, index, PRODUCTS, KEYWORD).search(
            SearchQuery("", category="Ring")
        )

        assert handles(groups) == ["bond-ring"]
        assert embedder.embedded_texts == []


class TestFallback:
    async def test_a_failing_embedder_falls_back_to_keyword_search(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        index = InMemoryVectorIndex()
        smart = HybridRetriever(FakeEmbedder(fail=True), index, PRODUCTS, KEYWORD)
        retriever = FallbackRetriever(smart, KeywordRetriever(KEYWORD))

        with caplog.at_level("WARNING"):
            groups = await retriever.search(SearchQuery("black clutch"))

        assert handles(groups)[0] == "lotus-black"  # keyword search answered instead
        assert "retrieval_fallback" in caplog.text
        assert "embedding service is down" in caplog.text

    async def test_a_failing_index_falls_back_too(self) -> None:
        embedder, index = await indexed()
        index.fail = True
        retriever = FallbackRetriever(
            HybridRetriever(embedder, index, PRODUCTS, KEYWORD), KeywordRetriever(KEYWORD)
        )

        assert handles(await retriever.search(SearchQuery("gold ring")))[0] == "bond-ring"

    async def test_an_empty_index_falls_back_instead_of_returning_nothing(self) -> None:
        retriever = FallbackRetriever(
            HybridRetriever(FakeEmbedder(), InMemoryVectorIndex(), PRODUCTS, KEYWORD),
            KeywordRetriever(KEYWORD),
        )

        assert handles(await retriever.search(SearchQuery("gold ring")))[0] == "bond-ring"

    async def test_without_a_fallback_the_error_surfaces(self) -> None:
        with pytest.raises(RetrievalError):
            await HybridRetriever(FakeEmbedder(fail=True), InMemoryVectorIndex(), PRODUCTS, KEYWORD).search(
                SearchQuery("gold ring")
            )


class TestEmbeddingIndexer:
    async def test_the_first_run_embeds_everything_and_the_second_run_embeds_nothing(self) -> None:
        embedder, index = FakeEmbedder(), InMemoryVectorIndex()
        indexer = EmbeddingIndexer(PRODUCTS, embedder, index, "fake-model")

        first = await indexer.run()
        second = await indexer.run()

        assert (first.embedded, first.unchanged) == (5, 0)
        assert (second.embedded, second.unchanged) == (0, 5)  # the content hash says nothing changed
        assert len(embedder.embedded_texts) == 5

    async def test_only_changed_products_are_re_embedded(self) -> None:
        embedder, index = FakeEmbedder(), InMemoryVectorIndex()
        await EmbeddingIndexer(PRODUCTS, embedder, index, "fake-model").run()

        edited = [
            *CATALOG[:2],
            make_product("bond-ring", title="Bond Ring", description="Now with diamonds"),
            *CATALOG[3:],
        ]
        report = await EmbeddingIndexer(InMemoryProducts(edited), embedder, index, "fake-model").run()

        assert (report.embedded, report.unchanged) == (1, 4)

    async def test_a_new_embedding_model_re_embeds_everything(self) -> None:
        embedder, index = FakeEmbedder(), InMemoryVectorIndex()
        await EmbeddingIndexer(PRODUCTS, embedder, index, "model-v1").run()

        report = await EmbeddingIndexer(PRODUCTS, embedder, index, "model-v2").run()

        assert report.embedded == 5
        assert {item.embedding_model for item in index.items.values()} == {"model-v2"}

    async def test_products_removed_from_the_catalog_are_removed_from_the_index(self) -> None:
        embedder, index = FakeEmbedder(), InMemoryVectorIndex()
        await EmbeddingIndexer(PRODUCTS, embedder, index, "fake-model").run()

        report = await EmbeddingIndexer(InMemoryProducts(CATALOG[:3]), embedder, index, "fake-model").run()

        assert report.deleted == 2
        assert set(index.items) == {"lotus-black", "lotus-gold", "bond-ring"}


def test_product_is_a_plain_value_object() -> None:
    assert isinstance(CATALOG[0], Product)


async def test_an_arabic_only_query_is_embedded_not_mistaken_for_an_empty_query() -> None:
    """Regression: the English tokenizer finds no tokens in Arabic, so it was once treated as empty."""
    embedder, index = await indexed()

    await HybridRetriever(embedder, index, PRODUCTS, KEYWORD).search(SearchQuery("خاتم دهب"))

    assert embedder.embedded_texts == ["خاتم دهب"]


async def test_filters_that_match_nothing_are_an_empty_answer_not_a_failure() -> None:
    embedder, index = await indexed()
    retriever = HybridRetriever(embedder, index, PRODUCTS, KEYWORD)

    assert await retriever.search(SearchQuery("gold ring", category="Spaceship")) == []  # no fallback needed
