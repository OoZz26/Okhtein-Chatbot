Implement issue **006 — Smarter matching (hybrid retrieval with pgvector)**.

First read `docs/prompts/_common.md` and `docs/issues/006-hybrid-retrieval.md`. Check the current
pgvector docs (https://github.com/pgvector/pgvector and the `pgvector` Python package) for exact
syntax — do not guess.

Suggested design:
- **Docker:** switch the Postgres image to `pgvector/pgvector:pg17` (same major version as
  `postgres:17`, so the existing named volume keeps working). Confirm data survives.
- **Domain ports** (`app/domain/ports.py`): `Embedder` (`embed(texts) -> list[list[float]]`) and
  `VectorIndex` (`upsert(items)`, `search(vector, filters, k) -> list[ScoredHandle]`,
  `indexed_hashes()`). Domain DTOs only.
- **Domain retrieval** — **Strategy** pattern behind a `Retriever` protocol:
  `KeywordRetriever` (existing logic moved behind the protocol), `VectorRetriever`,
  `HybridRetriever` (vector search with filters → keyword boost → group colour variants), and a
  `FallbackRetriever` that uses keyword search when the embedder or index fails (same
  Chain-of-Responsibility idea as the LLM fallback in 009 — reuse its error types if they fit).
- `app/domain/retrieval/product_text.py`: builds the rich text per product + its content hash.
- **Infra:** `app/infra/llm/openai_embedder.py` (`text-embedding-3-small`, batched);
  `app/infra/db/pgvector_index.py` with SQLAlchemy + `pgvector.sqlalchemy.Vector(1536)`:
  - `CREATE EXTENSION IF NOT EXISTS vector` at startup (in `init_storage`)
  - table `product_embeddings(handle PK, content_hash, embedding_model, category, price_min,
    available, title, embedding vector(1536), updated_at)`
  - HNSW index: `USING hnsw (embedding vector_cosine_ops)`
  - search: `WHERE` filters + `ORDER BY embedding <=> :query LIMIT :k`, returning distance
- **Script:** `scripts/build_embeddings.py` — loads the catalog, computes hashes, embeds only
  new/changed products (and when the model name changed), upserts, deletes products no longer in
  the catalog, prints counts.
- **Wiring:** strategy chosen by `Settings.retriever` (`keyword | vector | hybrid`) in the
  composition root; `search_products` tool uses the `Retriever`, not a concrete class.
- **Eval:** `scripts/eval_retrieval.py` with ~25 labelled queries in
  `tests/evals/retrieval_cases.json` (English, Arabic, occasion/gift queries, budget queries) →
  hit@3 per strategy side by side. Cache query embeddings in the eval to save cost.
- **Tests:** unit tests with `FakeEmbedder` (deterministic vectors) and an in-memory
  `FakeVectorIndex`; an integration test (`@pytest.mark.integration`) against real pgvector that
  checks filters + ordering.

Demo: `docker compose up -d` (data still there), `python scripts/build_embeddings.py` twice
(second run embeds 0), `EXPLAIN` of a search query showing the HNSW index, the eval table, and a
chat like "something bold for a wedding under 100k". Explain where each strategy wins or loses
and what HNSW does differently from brute force.
