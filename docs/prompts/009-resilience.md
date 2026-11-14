Implement issue **009 — Resilience: LLM fallback & graceful failure**.

First read `docs/prompts/_common.md` and `docs/issues/009-resilience.md`.

Suggested design:
- `app/infra/llm/openrouter_provider.py`: reuse the OpenAI adapter with a different base URL
  (`https://openrouter.ai/api/v1`), key and model — ideally one `OpenAICompatibleProvider` class
  configured twice (no copy-paste).
- `app/domain/llm/fallback_chain.py` (or services): `FallbackLLMProvider` implementing
  `LLMProvider` over an ordered list of providers — **Chain of Responsibility** + **Composite**.
  It classifies errors (transient → retry with exponential backoff + jitter, then next provider;
  non-transient → next provider) using domain error types the adapters raise, so the chain does
  not depend on OpenAI exception classes.
- Per-provider timeout from `Settings`.
- In the conversation service: if `AllProvidersFailed`, send a warm Arabic/English holding
  message, mark the chat for follow-up (store flag), and log the incident.
- `app/core/logging.py`: structured (JSON or key=value) logging with a filter that masks phone
  numbers / chat ids; log provider, latency and outcome per reply.
- Tests with fake providers that raise scripted errors.

Demo: put an invalid OpenAI key in `.env` (I will do it), restart, send a message, and show the
log line proving OpenRouter answered.
