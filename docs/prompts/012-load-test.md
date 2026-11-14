Implement issue **012 — Load test**.

First read `docs/prompts/_common.md` and `docs/issues/012-load-test.md`.

Suggested design:
- A `LOAD_TEST_MODE` setting that makes the composition root wire a `FakeLLM` (random 1–3 s
  latency, canned reply) and a recording `FakeGateway` instead of OpenAI and WAHA. Startup must
  refuse this mode when `ENVIRONMENT=production`. Webhook auth stays on (Locust signs requests).
- A small debug endpoint, enabled only in load-test mode, that returns the fake gateway's
  recorded sends so scenario B can be verified.
- `loadtests/locustfile.py`:
  - `CustomerUser`: unique chat id per user, sends realistic WAHA webhook payloads with think time.
  - `BurstUser`: sends 5 messages in under a second, then waits.
- `loadtests/check_bursts.py`: reads the recorded sends and asserts exactly one reply per burst.
- Headless command saving reports, e.g.
  `locust -f loadtests/locustfile.py --headless -u 100 -r 10 -t 2m --html loadtests/reports/a.html --csv loadtests/reports/a`.
- Scenario C: a tiny script that runs ~10 concurrent conversations through `/chat` against the
  real LLM and records p50/p95 latency, 429s and fallback usage.
- Write `docs/load-test-results.md` with the numbers and a short interpretation (where the
  bottleneck is and why).

Explain p50 vs p95, throughput vs concurrency, and why we fake the LLM in capacity tests.
