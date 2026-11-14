# 006 — Smarter matching (hybrid retrieval)

**Status:** ⚪ Todo · **Estimate:** 30 min

## What to build

Better product matching for fuzzy needs ("something bold for a wedding", "gift for my mum who
loves gold"). Retrieval becomes a swappable **strategy**:
- **Keyword** (the 002 search, kept as baseline and fallback)
- **Embedding**: semantic similarity over a rich text per product (title, category, colour,
  description, details, collections) using `text-embedding-3-small`
- **Hybrid** (default): hard filters first (category, budget, stock), then rank by embedding
  similarity with a keyword boost

Details:
- Product embeddings are computed offline by a script and cached in a file; they are rebuilt only
  when the catalog changes (content hash). 212 products → plain in-memory cosine similarity, no vector DB.
- The query embedding is computed per search; Arabic queries work.
- Colour variants of the same model are grouped so results are not three copies of one bag.
- If embeddings are unavailable, retrieval falls back to keyword search and logs it.
- A retrieval eval: ~25 labelled queries → hit@3 for each strategy, side by side.

## Acceptance criteria

- [ ] The retrieval eval prints hit@3 for keyword, embedding and hybrid
- [ ] Hybrid hit@3 ≥ 80% and ≥ keyword
- [ ] The strategy is chosen by configuration, no code change
- [ ] Embedding failure falls back to keyword (unit test with a failing fake embedder)
- [ ] Unit tests use a fake embedder, no network
- [ ] Results respect filters: no out-of-stock unless asked, never over budget
- [ ] Colour variants are grouped in results

## Blocked by

- 002 — Tracer bullet: chat over HTTP
