Implement issue **013 — README & demo**.

First read `docs/prompts/_common.md` and `docs/issues/013-readme-demo.md`, then the whole codebase.

Do:
- `README.md`: overview, architecture diagram (Mermaid: layers + ports + adapters + external
  systems), setup from zero (Docker Desktop, `.env`, `docker compose up -d`, WAHA QR scan,
  `build_embeddings`, run the app), testing (unit, integration, evals, load test), configuration
  table, and a **design patterns table** mapping each pattern to the real file/class that uses it
  (Adapter, Repository, Facade, Strategy, Chain of Responsibility, Command + Registry, State
  machine, Producer/Consumer + debounce, distributed lock, write-through, cache-aside, DI /
  composition root).
- `docs/demo-script.md`: 4–5 conversations to run live (vague → discovery → cards, cheaper one
  via memory, FAQ, handoff and release, returning customer) with expected behaviour.
- Cleanup: remove dead code and unused settings, make sure `.env.example` is complete, all
  checks green, link the latest eval and load-test reports.
- Verify the README by following it yourself step by step where possible, and list anything you
  could not verify.
