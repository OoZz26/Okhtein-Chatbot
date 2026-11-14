Implement issue **002 — Tracer bullet: chat over HTTP returns a real product link**.

First read `docs/prompts/_common.md` and `docs/issues/002-tracer-http-chat.md`.

Suggested design (adjust if you have a better idea, but explain why):
- `app/domain/models.py`: `Product` (frozen dataclass), `ChatMessage`, `AgentReply`.
- `app/domain/ports.py`: `ProductRepository` (get by handle, all), `LLMProvider`
  (`chat(messages, tools) -> LLMResponse` with optional tool calls). Domain-owned DTOs, not
  OpenAI types.
- `app/domain/retrieval/keyword.py`: keyword + filters (category, max price, in-stock).
- `app/domain/tools/`: a `Tool` protocol (name, JSON schema, `run(args)`) and a `ToolRegistry`
  (Command + Registry pattern). Only `search_products` for now. Tool results contain handle,
  title, colour, price, availability — the model never sees or builds URLs.
- `app/domain/agent/sales_agent.py`: tool loop with a max-rounds guard, structured final output
  (`AgentReply`), and validation that drops unknown handles (log a warning).
- `app/domain/agent/prompts/system_v1.md`: a minimal friendly system prompt (the full persona
  comes in 005 — keep this small).
- `app/infra/catalog/json_repository.py`, `app/infra/llm/openai_provider.py` (use structured
  outputs / JSON schema for the final answer).
- `app/services/chat_service.py`: `handle_message(chat_id, text) -> ChatResult` with links
  built from handles (`{store_url}/products/{handle}`).
- `app/api/chat.py` (`POST /chat`), `app/api/health.py`, `app/bootstrap.py` (composition root),
  `app/main.py` (FastAPI app factory).
- `tests/fakes.py`: `FakeLLM` that replays scripted responses (including tool calls).
- Enforce the dependency rule with a test that imports every `app.domain` module and asserts
  no forbidden third-party modules are imported (or ruff's banned-api rule).

Use the latest suitable OpenAI chat model from `Settings` (not hard-coded).

Demo: `uvicorn app.main:app --reload`, then a `curl` to `/chat` with "I want a black clutch
under 50000" and show the reply with links. Open one link to prove it is real.
