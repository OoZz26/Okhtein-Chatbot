Implement issue **006 — Smarter matching (hybrid retrieval)**.

First read `docs/prompts/_common.md` and `docs/issues/006-hybrid-retrieval.md`.

Suggested design:
- Domain: a `Retriever` protocol (`search(query: SearchQuery) -> list[Product]`) — **Strategy**
  pattern — with `KeywordRetriever` (existing logic moved behind the protocol),
  `EmbeddingRetriever`, and `HybridRetriever` (filters → embedding rank → keyword boost).
  An `Embedder` port; cosine similarity with numpy in the domain is fine (numpy is not infra).
- A `FallbackRetriever` (or similar) that uses keyword search when the embedder fails — the same
  Chain-of-Responsibility idea as the LLM fallback.
- `app/infra/llm/openai_embedder.py` using `text-embedding-3-small`.
- `scripts/build_embeddings.py`: builds one rich text per product, embeds in batches, saves
  vectors + a catalog content hash to `data/embeddings.npz` (or `.json`); skips if the hash matches.
- Group colour variants (same title) into one result showing the available colours.
- Strategy selected by `Settings.retriever` in the composition root.
- `scripts/eval_retrieval.py` with ~25 labelled queries in `tests/evals/retrieval_cases.json`
  (English, Arabic, occasion/gift-style queries, budget queries) → hit@3 per strategy, printed side by side.

Show the eval table at the end and explain where each strategy wins or loses.
