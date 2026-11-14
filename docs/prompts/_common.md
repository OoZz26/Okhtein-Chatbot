# Shared build rules (read before implementing any issue)

You are implementing one vertical slice of the **Okhtein WhatsApp sales bot**: a friendly AI
stylist that chats with customers of Okhtein (Egyptian luxury accessories, https://eg.okhtein.com)
on WhatsApp, discovers what they want, and sends matching product links.

Stack: Python 3.11+, FastAPI, OpenAI (primary) + OpenRouter (fallback, OpenAI-compatible),
WAHA (self-hosted unofficial WhatsApp gateway, Docker), Redis (short-term chat history,
debounce, locks), Postgres (long-term history, customer profiles, handoff state).

## Read first
1. `docs/issues/README.md` — architecture, dependency rule, SOLID and clean-code rules. **Binding.**
2. The issue file you were given in `docs/issues/`.
3. The current code, so you extend what exists instead of duplicating it.
4. Data: `data/products.json` (212 products), `data/categories.json`, `data/knowledge.md`.

## How to work
- **This is a learning project.** The developer wants to understand every piece. Before writing
  code, give a short plan: the files you will create or change, the ports/classes, and which
  design pattern each one uses and why (3–8 bullets). Then implement in small steps, explaining
  each file in 1–3 sentences as you go.
- **Stay inside the slice.** Build the thinnest version that meets the acceptance criteria. Do not
  start features that belong to other issues; note ideas as "Later" instead.
- **Test-first where it is natural** (domain logic, services). Tests use fakes of ports
  (`FakeLLM`, `FakeGateway`, fakeredis), not mocks of internals. No network in unit tests.
- **Dependency rule:** `api → services → domain ← infra`. The domain never imports `openai`,
  `fastapi`, `redis`, `sqlalchemy` or `httpx`. New external systems get a port in the domain and
  an adapter in infra. Wiring only in the composition root.
- **Config only through `Settings`.** No hard-coded secrets, URLs or magic numbers.
- **Secrets:** never ask the developer to paste API keys into the chat. Ask them to put keys in
  `.env` themselves.
- **WhatsApp safety:** only use the test number; never send messages to anyone else.

## Definition of done
1. Every acceptance criterion in the issue is met (tick the boxes in the issue file).
2. These pass, and you show the output:
   ```
   ruff check . && ruff format --check . && mypy app && pytest
   ```
3. Update the issue's status line and its row in `docs/issues/README.md` to ✅ Done.
4. Commit on the main branch with a message like `feat(002): tracer bullet chat over HTTP`.
5. Finish with a short report: what was built, the patterns used and why, **how to demo it**
   (exact commands), anything not done or not verified, and "Later" ideas.
