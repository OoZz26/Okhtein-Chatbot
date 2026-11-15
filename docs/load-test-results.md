# Load test results

Measured on the developer machine (Windows 11, Docker Desktop, Postgres/Redis in containers, one uvicorn
process). Reproduce with the commands at the bottom.

## Why we test the way we do

The real bottleneck of this system is the **LLM API**: seconds per reply, rate limits, and money per call.
WhatsApp cannot be load-tested at all (one real number, ban risk). So we split the question in three:

| | Question | LLM | WhatsApp | What is measured |
|---|---|---|---|---|
| A | How much can *our* code absorb? | fake, 1-3 s latency | recording fake | webhook latency and errors |
| B | Is it *correct* under concurrency? | fake | recording fake | one reply per burst |
| C | What does the *real* LLM do? | real | none (`/chat`) | real latency, 429s, fallback |

**Why fake the LLM in capacity tests:** a real model would measure OpenAI, not our code; it would cost
money on every simulated message; and it would hit rate limits long before our code is stressed. The fake
waits 1-3 seconds like a real model, so our code still has to hold hundreds of in-flight replies, but the
answer is free and repeatable. Load mode is also guarded: the `Settings` object refuses to be created with
`LOAD_TEST_MODE=true` and `ENVIRONMENT=production`.

## Scenario A: capacity (100 simulated customers, 2 minutes)

| metric | result | target |
|---|---|---|
| webhook requests | 2,479 | |
| failures | **0 (0.00%)** | 0% |
| p50 latency | **4 ms** | |
| p95 latency | **23 ms** | < 100 ms |
| p99 latency | 43 ms | |
| slowest request | 117 ms | |
| throughput | 20.8 requests/s | |

Reports: `loadtests/reports/a.html` (charts) and `a_stats.csv`.

**p50 vs p95.** p50 (the median) is the typical request: half were faster than 4 ms. p95 is what the
unluckiest 1 in 20 experienced: 23 ms. Averages hide trouble; a service can have a lovely average and a
terrible p95. We judge a webhook by its p95 because WAHA retries slow or failed deliveries, so the tail is
what causes duplicates and noise.

**Throughput vs concurrency.** Concurrency is how many customers are active at once (100). Throughput is how
many requests per second the server completes (about 21). Each simulated customer thinks for 3-8 seconds
between messages, so 100 customers produce about 20 requests/s, and the server was nowhere near saturated
(latency stayed flat). To find the breaking point you would raise users until p95 climbs; this run proves
the target, not the ceiling.

**Why the webhook is so fast while a reply takes seconds.** The webhook only verifies the signature, parses
the event and schedules the work, then answers immediately. The reply (LLM call, sending) happens afterwards
in the background, behind a debounce and a per-chat lock. That design is what keeps the webhook flat even
while 100 replies are being generated.

## Scenario B: correctness under concurrency

20 of the 100 simulated customers were "burst" customers: 5 messages in well under a second from a fresh
chat, repeatedly. **160 bursts (800 messages): every burst received exactly one reply**, verified from the
fake gateway's recorded sends (`loadtests/check_bursts.py`). No burst produced two replies and none was
dropped. This exercises the Redis buffer, the latest-wins debounce and the per-chat lock under real
concurrency.

## Scenario C: real LLM smoke test (10 concurrent conversations, 2 messages each)

| metric | result |
|---|---|
| replies | 20 |
| wall time | 59.9 s |
| latency per reply | **p50 22.5 s, p95 38.8 s**, max 38.8 s |
| HTTP errors | 0 |
| holding messages ("one moment...") | 0 |
| retries (429 / 5xx) | 0 |
| provider failures / fallback to OpenRouter | 0 / 0 |
| semantic search fell back to keyword | 0 |

**Interpretation.** Nothing failed and nothing was throttled at this size, but the numbers show where the
time goes: **a real reply takes 20-40 seconds under 10 concurrent conversations, against 4 ms for our own
code.** A reply needs two or three sequential model calls (decide to search, read results, write the
answer) and each takes roughly 6-13 seconds with `gpt-5-mini` (the per-call latency is in the log as
`llm_call ... latency_ms=`). So the LLM is about 99.9% of the time. This is exactly why the design
acknowledges the webhook immediately, shows "typing...", and batches bursts into one reply: the customer
waits on the model, so the bot must feel alive while it works.

Things to do if replies need to be faster (not done, see "Later"): a faster/smaller model for simple turns,
fewer tool rounds (the prompt already limits searches), streaming is not available on WhatsApp, and prompt
caching for the long system prompt. The fallback provider (OpenRouter) was not used because the primary
never failed; its behaviour is covered by unit tests with scripted errors.

## A measurement trap worth remembering

The first Scenario A run showed p95 = **2,100 ms** and looked like a failure. The app was fine: the
simulated customers connected to `localhost`, which on Windows resolves to IPv6 (`::1`) first; nothing
listens there, and the failed attempt costs about 2 seconds before falling back to IPv4. Every *new
connection* paid that, while requests on an open connection took 4-7 ms. Pointing the test at `127.0.0.1`
fixed it (p95 23 ms). Lesson: check what you are measuring before tuning the system.

## Reproduce

```bash
# Scenarios A and B: starts an isolated app on :8001 in load-test mode, runs Locust, verifies bursts, cleans up
python scripts/run_load_test.py                     # 100 customers, 2 minutes

# Scenario C: the real app must be running (uvicorn app.main:app --host 0.0.0.0 --port 8000)
python loadtests/real_llm_smoke.py --base-url http://127.0.0.1:8000 --log uvicorn.log
```

The runner uses its own Redis database (14) and a fake gateway, and deletes the simulated customers
(chat ids starting with `2999`, never an Egyptian number) from Postgres afterwards. At the end of a Locust
run you may see an `I/O operation on closed file` traceback from Locust's CSV writer; it is a harmless
Locust shutdown quirk and the reports are complete.

## Later

- Find the ceiling: run with 500-1000 users and watch where p95 bends (probably the single uvicorn process
  or Postgres connections, not Redis).
- Run several uvicorn workers; the Redis lock and sequence counters already make the debouncer safe across
  processes, but the in-memory sender-name map in the debouncer would move to Redis.
- Try a faster model for short turns and measure the effect on Scenario C.

## What the load test does NOT measure: the outgoing send limit

`scripts/run_load_test.py` sets `SEND_RATE_LIMIT_PER_MINUTE` to 1,000,000, because the fake gateway sends
nothing real. In production the limit is **one counter shared by every chat** (default 60/min since the
post-build review). A reply is up to `MAX_BUBBLES` texts plus one message per product card, so the real
ceiling is roughly 8–15 replies per minute for the whole business number. When it is reached, replies
wait for the next minute; they are not lost (the chat lock is renewed while waiting, and messages sent
meanwhile are picked up after the reply). Raise it only as far as the WhatsApp number can safely send.
