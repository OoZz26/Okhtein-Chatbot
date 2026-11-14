Implement issue **005 — Discovery & friendliness ("Nour")**. This is the most important slice:
"super friendly" is the client's top requirement.

First read `docs/prompts/_common.md` and `docs/issues/005-discovery-friendliness.md`.

Suggested design:
- Prompt files in `app/domain/agent/prompts/` (versioned, e.g. `system_v2.md`): persona,
  tone guide (do / don't table), discovery rules, WhatsApp format rules, boundaries, and 4–6
  short few-shot conversations in Egyptian Arabic and English (including a vague request, a
  specific one, an impatient one, and a gift). Models copy examples better than adjectives.
- Domain: `ConversationStage` enum and a small state machine with allowed transitions;
  `CustomerProfile` (slots) with a pure `apply(updates)` method; `AgentReply` extended with
  `stage` and `profile_updates`.
- A `DiscoveryPolicy` in the domain that enforces the hard rules in code, not only in the prompt
  (e.g. after 3 discovery questions, instruct the agent to recommend). Keep it a pure, tested class.
- Session state (stage, profile, questions asked) stored via a `SessionStore` port with a Redis
  adapter (`chat:{id}:session`, same TTL as history).
- Pass the customer's WhatsApp display name and the current profile into the prompt.
- Eval harness in `tests/evals/`: YAML/JSON scenarios (customer turns + rule expectations),
  a runner that talks to the real agent, rule checks in code, and an LLM judge with a rubric
  (warmth, natural dialect, not pushy, brevity, helpfulness; 1–5, with a short reason). One
  command (e.g. `python -m tests.evals.run_conversations`) prints a table and saves a report to
  `tests/evals/reports/`.
- Scenarios: vague Arabic, specific English with budget, impatient, gift for mum, Franco-Arabic,
  off-topic/prompt injection, gender-neutral check.

Run the evals, show the report, and iterate on the prompt until the targets are met. Tell me
which prompt changes moved the scores — that is the most valuable lesson of this slice.
