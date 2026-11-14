# 002 — Tracer bullet: chat over HTTP returns a real product link

**Status:** ⚪ Todo · **Estimate:** 35 min

## What to build

The thinnest end-to-end path through the whole brain. A message sent to an HTTP chat endpoint
(chat id + text) comes back as a short, friendly reply that recommends real, in-stock Okhtein
products with their correct links.

The path, kept deliberately simple:
- The catalog is loaded from the extracted product data behind a product-repository port.
- A plain keyword + filter search (category, max price, in stock) — smart retrieval comes in 006.
- The sales agent calls the LLM through an LLM-provider port (OpenAI adapter) with a single
  `search_products` tool, loops until the model stops calling tools, and returns structured output.
- A safety check drops any product the model mentions that is not in the catalog, so the bot can
  never send an invented link. Links are built by our code from the handle, never by the model.
- Stateless: no memory yet (004), no WhatsApp yet (003).
- A `FakeLLM` implementing the same port makes the agent testable with no network.
- A health endpoint reports the app is up.

Structured agent output (decision, keep this shape and extend it later):
```
AgentReply:
  message: str               # what the customer reads
  product_handles: list[str] # products recommended in this turn; links built from these
```

## Acceptance criteria

- [ ] Sending "I want a black clutch" to the chat endpoint returns a reply containing at least one link that exists in the catalog
- [ ] Out-of-stock products are not recommended unless the customer asks for them
- [ ] A budget in the request ("under 50,000") is respected by search results
- [ ] If the LLM returns an unknown handle or URL, it is removed and logged (unit test with `FakeLLM`)
- [ ] The agent's tool loop is unit-tested with `FakeLLM` (tool call → tool result → final answer), no network
- [ ] The domain layer imports neither `openai` nor `fastapi` (enforced by a test or lint rule)
- [ ] One API-level test hits the chat endpoint with the fake LLM wired in through dependency injection
- [ ] Manual demo: a `curl` / Swagger call with the real OpenAI key returns a sensible recommendation

## Blocked by

- 001 — Project foundation
