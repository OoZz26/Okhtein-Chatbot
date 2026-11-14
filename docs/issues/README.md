# Okhtein WhatsApp Bot — Issue Backlog

The bot is built as **vertical slices (tracer bullets)**: every issue cuts through all layers
(WhatsApp/HTTP → service → agent → retrieval → storage → tests) in a thin form and is
**demoable on its own**. Early slices are crude but end-to-end; later slices make one part smarter.

- Issues: this folder, one markdown file per slice.
- Build prompts: [`../prompts/`](../prompts/) — paste the matching prompt into a new Claude Code
  session (or this one) to implement an issue. Shared rules live in
  [`../prompts/_common.md`](../prompts/_common.md).
- An issue is **done** only when every acceptance criterion passes and `ruff`, `mypy` and
  `pytest` are green.

## Slices

| # | Slice | Blocked by | Est. | Status |
|---|---|---|---|---|
| 001 | [Project foundation (prefactor)](001-project-setup.md) | — | 20m | ✅ Done |
| 002 | [Tracer bullet: chat over HTTP returns a real product link](002-tracer-http-chat.md) | 001 | 35m | ✅ Done |
| 003 | [Tracer bullet over WhatsApp](003-tracer-whatsapp.md) | 002 | 30m | ✅ Done |
| 004 | [Bot remembers the conversation](004-conversation-memory.md) | 002 | 30m | ✅ Done |
| 005 | [Discovery & friendliness ("Nour")](005-discovery-friendliness.md) | 004 | 45m | ✅ Done |
| 006 | [Smarter matching (hybrid retrieval)](006-hybrid-retrieval.md) | 002 | 30m | ⚪ Todo |
| 007 | [Store FAQ answers](007-store-faq.md) | 002 | 10m | ✅ Done |
| 008 | [Human-like WhatsApp experience](008-human-like-whatsapp.md) | 003, 004 | 30m | ⚪ Todo |
| 009 | [Resilience: LLM fallback & graceful failure](009-resilience.md) | 002 | 20m | 🔵 In progress |
| 010 | [Human handoff](010-human-handoff.md) | 003, 004 | 20m | ⚪ Todo |
| 011 | [Returning customer](011-returning-customer.md) | 005 | 15m | ⚪ Todo |
| 012 | [Load test](012-load-test.md) | 008 | 20m | ⚪ Todo |
| 013 | [README & demo](013-readme-demo.md) | all | 10m | ⚪ Todo |

Statuses: ⚪ Todo · 🟡 Ready · 🔵 In progress · ✅ Done

**Critical path:** 001 → 002 → 003 gives a working WhatsApp bot in ~1h15. After that 004, 006,
007 and 009 only need 002 and can go in any order. If time runs out, drop from the bottom:
011, then the image cards in 008.

```
001 ─► 002 ─┬─► 003 ─┬─► 008 ─► 012
            │        └─► 010
            ├─► 004 ─┬─► 005 ─► 011
            │        ├─► 008
            │        └─► 010
            ├─► 006
            ├─► 007
            └─► 009                    013 after all
```

## Engineering principles (apply to every slice)

### Layers and the dependency rule
```
api  ──►  services  ──►  domain  ◄──  infra
(HTTP,    (use cases)    (business     (Redis, Postgres,
 webhook)                 rules+ports)  OpenAI, WAHA, files)
```
- **domain** — models, agent logic, retrieval, tools, prompts. Imports **nothing** from infra,
  api or third-party SDKs. Defines **ports** (`typing.Protocol`): `LLMProvider`,
  `ProductRepository`, `ChatHistoryStore`, `MessagingGateway`, `Embedder`, ...
- **infra** — adapters that implement the ports: `OpenAIProvider`, `RedisHistoryStore`,
  `WahaGateway`, `JsonProductRepository`, ...
- **services** — orchestrate use cases ("handle an incoming message") through ports only.
- **api** — thin: parse, call a service, respond. No business logic.
- **Composition root** — all wiring in one place (`app/bootstrap.py` + FastAPI `Depends`).

### SOLID in this project
| Principle | Here |
|---|---|
| **S**ingle responsibility | `WahaGateway` only talks to WAHA; `Debouncer` only debounces |
| **O**pen/closed | New LLM tool or retriever = new class registered, not a new `elif` |
| **L**iskov substitution | `FakeLLM` and `OpenAIProvider` are interchangeable wherever `LLMProvider` is expected |
| **I**nterface segregation | Small ports: reading products is separate from anything that writes |
| **D**ependency inversion | Services depend on `ChatHistoryStore`, never on `redis.Redis` |

### Clean code rules
- Type hints everywhere; `mypy --strict` for `app/domain` and `app/services`.
- Small functions (aim < 25 lines), intention-revealing names, no magic numbers (use `Settings`).
- No global mutable state; config only via `Settings` (pydantic-settings, `.env`).
- Domain exceptions in one module; never swallow exceptions silently.
- Pydantic at the edges (API, LLM structured output); dataclasses inside the domain.
- `logging`, never `print`, inside `app/`. Never log secrets; mask phone numbers.
- Prompts are versioned text files, not giant inline strings.
- Every behaviour has a test; tests use **fakes of ports**, not mocks of internals.
- `ruff` formats and lints; formatting is not up for debate.
