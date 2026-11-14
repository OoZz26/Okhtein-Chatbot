# 012 — Load test

**Status:** ✅ Done · **Estimate:** 20 min

## What to build

Prove the system holds up and stays correct under load, measured with Locust.

Key idea: the real bottleneck is the LLM API (seconds per reply, rate limits, cost) and WhatsApp
cannot be load-tested (one number, ban risk). So:

- **A. Capacity:** simulated customers send webhook payloads to our app, with a fake LLM that
  waits 1–3 s and a fake messaging gateway. Measures webhook latency (p50/p95), error rate and throughput.
- **B. Correctness under concurrency:** each simulated customer sends bursts of 5 messages in a
  second; every burst must get exactly one reply.
- **C. Real-LLM smoke:** ~10 concurrent conversations against the real API to observe real
  latency, rate limiting and the fallback.

The fake-LLM / fake-gateway load mode must be impossible to enable in production.

## Acceptance criteria

- [x] One command runs scenario A headless and saves an HTML + CSV report
- [x] 100 simulated customers: webhook p95 < 100 ms and 0% errors
- [x] Scenario B: exactly one reply per burst, verified from recorded fake-gateway sends
- [x] Scenario C results (latency p50/p95, any 429s, fallback used?) written to a short results doc
- [x] Load mode refuses to start when the environment is production

## Blocked by

- 008 — Human-like WhatsApp experience

Results and interpretation: [`docs/load-test-results.md`](../load-test-results.md). Run it with `python scripts/run_load_test.py`.
