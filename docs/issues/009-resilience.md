# 009 — Resilience: LLM fallback & graceful failure

**Status:** 🔵 In progress (manual OpenRouter demo pending) · **Estimate:** 20 min

## What to build

The bot keeps working when a provider fails, and a customer never sees an error or silence.

- **Provider chain:** OpenAI first, OpenRouter second (same OpenAI-compatible interface). Each
  provider has a timeout and retries transient errors (429, 5xx, timeouts) with exponential backoff
  before the chain moves on. The chain itself implements the LLM-provider port, so the agent does
  not know there is more than one provider.
- **Graceful failure:** if every provider fails, the customer gets a warm "one moment, I'll get
  back to you" message and the chat is flagged for follow-up.
- **Observability:** structured logs per reply with provider used, latency, tool calls and
  outcome. No secrets in logs; phone numbers masked.

## Acceptance criteria

- [x] Primary raises → fallback answers (unit test with fake providers)
- [x] Transient error is retried before falling back; non-transient error falls back immediately (tests)
- [x] All providers fail → friendly message sent, no stack trace to the customer, chat flagged (test)
- [ ] Manual: an invalid OpenAI key in `.env` → the bot still answers through OpenRouter
- [x] Timeouts, retries and provider order are configurable
- [x] Logs show the provider per reply; phone numbers are masked

## Blocked by

- 002 — Tracer bullet: chat over HTTP
