Implement issue **007 — Store FAQ answers**.

First read `docs/prompts/_common.md` and `docs/issues/007-store-faq.md`.

Suggested design:
- Domain port `StoreInfoSource` (`get_knowledge() -> str`) with a file adapter reading
  `data/knowledge.md`, cached with a reload method (or mtime check).
- Either inject the knowledge into the system prompt (it is small) or expose a `get_store_info`
  tool registered in the existing `ToolRegistry` — pick one, and explain the trade-off
  (prompt size and cost vs. one extra tool round).
- Prompt rule: answer store questions only from this knowledge; if missing, say so kindly and
  offer a team member (the handoff tool arrives in 010 — for now just say a team member will confirm).
- Ignore the "TODO for the store owner" section when answering (those values are unknown).
- Add two eval scenarios (returns policy = known; shipping fee = unknown) to the 005 harness if it
  exists, otherwise as tests with a fake LLM checking the prompt contains the knowledge.

Demo: ask "can I return an item?" and "how much is shipping?" in Arabic.
