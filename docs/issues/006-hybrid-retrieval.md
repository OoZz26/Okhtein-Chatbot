# 006 — Smarter matching (hybrid retrieval with pgvector)

**Status:** ⚪ Todo · **Estimate:** 40 min

## What to build

Better product matching for fuzzy needs ("something bold for a wedding", "gift for my mum who
loves gold"), using **pgvector** — vector search inside the Postgres we already run. This is the
setup many medium-size production systems use, and it scales far beyond Okhtein's catalog.

Retrieval becomes a swappable **strategy**:
- **Keyword** (the 002 search, kept as baseline and fallback)
- **Vector**: semantic similarity between the query and a rich text per product (title, category,
  colour, description, details, collections), embedded with `text-embedding-3-small` (1536 dims)
- **Hybrid** (default): hard filters (category, budget, stock) and vector ranking **in one SQL
  query**, then a keyword boost for exact name matches

Details:
- The Postgres image includes the pgvector extension (same Postgres major version, so existing
  data survives). The extension and a product-embeddings table are created at startup.
- An **HNSW index** with cosine distance on the embedding column (learning point: approximate
  nearest-neighbour index vs. brute force).
- An indexing script embeds products and upserts them; it only re-embeds products whose content
  changed (content hash) and records which embedding model produced each vector (versioned embeddings).
- Product facts used for filtering (price, stock, category) are stored next to the vector so
  filters and similarity run together in the database.
- The query embedding is computed per search; Arabic queries work.
- Colour variants of the same model are grouped so results are not three copies of one bag.
- If embeddings or pgvector are unavailable, retrieval falls back to keyword search and logs it.
- A retrieval eval: ~25 labelled queries → hit@3 for each strategy, side by side.

Ports involved (decision): an `Embedder` (text → vector) and a `VectorIndex`
(upsert products, search by vector with filters, top k). The domain's hybrid retriever depends
only on these ports; pgvector is one adapter, so a future move to another engine is one new class.

## Acceptance criteria

- [ ] `docker compose up -d` runs Postgres with pgvector; existing chat data is still there
- [ ] The indexing command embeds all products; a second run re-embeds nothing (hash check)
- [ ] Vector search uses an HNSW index (shown with `EXPLAIN` in the demo)
- [ ] Budget, stock and category filters are applied in the same query as vector ranking
- [ ] The retrieval eval prints hit@3 for keyword, vector and hybrid; hybrid ≥ 80% and ≥ keyword
- [ ] The strategy is chosen by configuration, no code change
- [ ] Embedder or pgvector failure falls back to keyword search (unit test with failing fakes)
- [ ] Unit tests use a fake embedder and an in-memory fake vector index, no network; an integration test runs against real pgvector
- [ ] Colour variants are grouped in results

## Blocked by

- 002 — Tracer bullet: chat over HTTP
