# 006 — Smarter matching (hybrid retrieval with pgvector)

**Status:** ✅ Done · **Estimate:** 40 min

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

- [x] `docker compose up -d` runs Postgres with pgvector; existing chat data is still there
- [x] The indexing command embeds all products; a second run re-embeds nothing (hash check)
- [x] Vector search uses an HNSW index (shown with `EXPLAIN` in the demo)
- [x] Budget, stock and category filters are applied in the same query as vector ranking
- [x] The retrieval eval prints hit@3 for keyword, vector and hybrid; hybrid ≥ 80% and ≥ keyword
- [x] The strategy is chosen by configuration, no code change
- [x] Embedder or pgvector failure falls back to keyword search (unit test with failing fakes)
- [x] Unit tests use a fake embedder and an in-memory fake vector index, no network; an integration test runs against real pgvector
- [x] Colour variants are grouped in results

## Blocked by

- 002 — Tracer bullet: chat over HTTP

## Results and lessons (measured on 25 labelled queries, hit@3)

| strategy | hit@3 | notes |
|---|---|---|
| keyword | 60% | Fails on synonyms ("sunglasses" vs "Shades"), descriptions ("something to wear on my wrist") and every Arabic query. |
| vector | 84% | Understands meaning and Arabic. Weak where the catalog is thin (few bracelets) or the query is very generic. |
| hybrid | 84% | Vector ranking plus a boost for exact name/colour words and variant grouping. Equal to vector on this set; the boost matters more for exact product-name queries. |

- **HNSW vs brute force:** brute force compares the query with every row (exact, slower as the catalog grows). HNSW walks a layered graph of nearest neighbours: much faster at scale, slightly approximate. At 212 products either is instant; the index is here as the production habit. `EXPLAIN` shows `Index Scan using ix_product_embeddings_embedding_hnsw`.
- **A bug the eval caught:** the hybrid retriever first decided "nothing to embed" using the English-only tokenizer, which routed every Arabic query to keyword browsing (hybrid 76% < vector 84%). A regression test covers it.
- **A bug the live chat caught:** the model passed an invented category ("wedding"); zero filtered hits was treated as "index broken". Now only an index that is empty even without filters counts as a failure, and the search tool ignores categories that are not in the catalog (telling the model the valid ones).
- Misses left: "a small bag for a wedding", "something to wear on my wrist", and two Arabic queries (`خاتم دهب`, `عايزة شنطة سهرة`). In real chats the model translates to English first, which the prompt already requires.
