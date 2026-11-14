# Morning checklist

Good morning. Everything from the backlog (slices 001 to 013) was built overnight, one commit per slice, with
`ruff`, `mypy` and `pytest` green at every commit. Final state: **268 unit tests + 14 integration tests pass**, the
conversation evals meet their targets (17 scenarios, average 4.85), and the app is **already running** on
port 8000 with the final code. Docker is up, your WhatsApp session is still linked (WORKING), and nothing was
sent to anyone: all conversation tests ran over `/chat` or with fakes.

## What was done, per slice

| Slice | Commit | What you get |
|---|---|---|
| 001 Foundation | `09d7665` | Layered skeleton, ruff/mypy/pytest, typed settings, Docker (Postgres, Redis, WAHA), health check |
| 002 Chat over HTTP | `ff8800c` | `POST /chat`, sales agent with a search tool, links built by code (the model can never invent one) |
| 003 WhatsApp | `7fe24cb` | Signed webhook, WAHA gateway, dedupe, ignores groups/status/own messages, allow-list |
| 004 Memory | `b44de6e` | Redis short-term + Postgres long-term, write-through and cache-aside |
| 005 Nour | `4ee9dd1` | Persona prompt, discovery (max 3 questions), conversation evals with an LLM judge |
| 009 Resilience | `446233b` | OpenAI → OpenRouter fallback with retries, warm holding message, follow-up flag, masked logs |
| 007 Store FAQ | `5b7b165` | Answers only from `data/knowledge.md` (live reload); unknown topics → "a team member will confirm" |
| 008 Human-like | `bb40062` | Debounce (burst → one reply), per-chat lock, typing, bubbles, product image cards, rate limit |
| 010 Handoff | `baafc2e` | Hand off on order tracking/complaints/"a person", silent while handed off, staff takeover, release endpoint |
| 006 Hybrid search | `9d7be8d` | pgvector + HNSW, hybrid retrieval (84% hit@3 vs keyword 60%), keyword fallback |
| 011 Returning customer | `5b9f713` | Remembers taste across visits, "welcome back", doesn't repeat shown products |
| 012 Load test | `c7ed9d7` | Locust: webhook p95 **23 ms**, 0 failures at 100 customers; 160/160 bursts got one reply |
| 013 README | `64002b0` | `README.md` (diagrams, setup, patterns table), `docs/demo-script.md`, cleanup |

Things worth knowing that changed under you:
- **Postgres image** is now `pgvector/pgvector:0.8.7-pg17-trixie` (same major version; your data was backed up and is intact).
- **Postgres is on host port 5433** in your `.env` (a native Windows Postgres owns 5432).
- WAHA now also subscribes to `message.any` events (needed to notice a person replying from the business phone).
- Settings added with safe defaults (all in `.env.example`); see the per-slice sections below.

## What still needs you (all manual, none blocks the bot)

1. **Add to `.env`** (optional but recommended): `OPENROUTER_API_KEY` (for the fallback), `ADMIN_API_KEY` (to release handed-off chats), `STAFF_PHONE` (who gets handoff alerts). Restart the app after editing.
2. **Phone checks** (details in the sections below, ~10 minutes in total):
   - 008: three quick messages → one reply, typing indicator, product image cards.
   - 010: handoff, silence, release, and the **staff takeover** check (the one thing I could not verify: WAHA's `source: app` flag for messages typed on the phone).
   - 009: the invalid-key → OpenRouter demo (needs an OpenRouter key).
   - 011 (optional): welcome-back after the session expires.
   - 013: run `docs/demo-script.md` end to end.
3. Nothing else: no secrets were touched, no WhatsApp messages were sent.

## How to start and test everything (in order)

Everything is already running. If you restart your machine, start it again like this:

```bash
cd "O:/Freelance Work/okhtein chatbot"
source .venv/Scripts/activate
docker compose up -d                                  # Postgres+pgvector, Redis, WAHA (session persists)
python scripts/check_infra.py                          # expect ✅ ✅ ✅
uvicorn app.main:app --host 0.0.0.0 --port 8000        # 0.0.0.0 so WAHA in Docker can reach it
```

Then, from the **second phone** (a number in `ALLOWED_NUMBERS`), message the linked number and follow
`docs/demo-script.md`. If the bot does not answer, read `uvicorn.log`: "sender not in the allowed list" means the
phone is identified by an internal `…@lid` id; add that id to `ALLOWED_NUMBERS` (the log with masked digits plus
the WAHA dashboard's Event Monitor show it).

Quality gate and extras:

```bash
ruff check . && ruff format --check . && mypy app && pytest     # unit tests
pytest -m integration                                           # real Redis/Postgres/pgvector
python -m tests.evals.run_conversations                         # real-LLM conversation evals (costs a few cents)
python scripts/eval_retrieval.py                                # keyword vs vector vs hybrid
python scripts/run_load_test.py                                 # load test (isolated app on :8001)
```

Known non-blocking things: `docs/load-test-results.md` explains why replies take 10-40 s (the LLM); the
conversation evals have a ~1-in-5 flake where an English customer sometimes gets an Arabic word (`gift_for_mum`).

---

## Details per slice (manual steps)

_(the sections below were written as each slice finished)_

### 009: Resilience (needs an OpenRouter key and one `.env` edit)
The fallback chain is tested with scripted failures; the live proof needs your accounts:
1. Create a free OpenRouter key and add `OPENROUTER_API_KEY=` to `.env`.
2. Temporarily change `OPENAI_API_KEY` to something invalid (for example `sk-invalid`), restart the app, send a message from the second phone.
3. `uvicorn.log` should show `llm_provider_failed provider=openai outcome=fallback` and then `llm_call provider=openrouter ... outcome=ok`, and the customer still gets an answer.
4. **Restore your real `OPENAI_API_KEY` and restart.**
(The OpenRouter model was not run through the friendliness evals; its tone may differ from `gpt-5-mini`.)

### 008: Human-like WhatsApp (needs your phone)
Start the stack first (see the commands at the top once the summary is written), then from a **second phone** (an allowed number) message the linked WhatsApp number:
1. **Burst:** send three quick messages in a row, e.g. `hi` / `I want a bag` / `for a wedding`. You should get **one** reply, about 4 seconds after your last message (`DEBOUNCE_SECONDS`), that addresses all three.
2. **Typing:** the chat should show "typing…" before the reply arrives.
3. **Cards:** ask for something specific (`a black clutch under 60000`). After the text you should receive **one image per product** with a caption: name, price and the real link. Tap a link to check it opens.
4. If images do not arrive but text links do, the image fallback worked (check `uvicorn.log` for `Image failed ... sending a text link`).
New `.env` settings: none are required (defaults are in `.env.example`: `LOCK_TTL_SECONDS`, `LOCK_WAIT_SECONDS`, `MAX_BUBBLES`, `TYPING_SECONDS_PER_CHAR`, `TYPING_MAX_DELAY_SECONDS`, `SEND_RATE_LIMIT_PER_MINUTE`).

### 010: Human handoff (needs your phone and two `.env` lines)
**Already done overnight:** the compose file subscribes WAHA to `message.any` events (needed to notice staff replies) and the WAHA container was recreated; your WhatsApp session stayed linked (WORKING).
Add to `.env` (both optional but needed for the checks below):
- `ADMIN_API_KEY=` any long random string (protects the release endpoint).
- `STAFF_PHONE=` the WhatsApp number (digits with country code) that should get handoff alerts. Leave it empty to only log them.

Checks (from the second phone, an allowed number):
1. Send `Where is my order?`. The bot should say a team member will reply here. If `STAFF_PHONE` is set, that number gets a "🔔 A customer needs a person" message with the reason and summary. The same line is in `uvicorn.log` (`handoff chat=… reason=…`).
2. Send another message: the bot must stay **silent** (no typing, no reply).
3. Release it (replace the chat id with the customer's, e.g. `201001234567@c.us`):
   ```bash
   curl -X POST "http://localhost:8000/admin/chats/201001234567@c.us/release" -H "X-Admin-Key: YOUR_ADMIN_API_KEY"
   ```
   Expect `{"chat_id": "...", "released": true}`, then the bot answers again.
4. **Staff takeover (the unverified one):** on the business phone (the linked WhatsApp), open that customer's chat and type a reply yourself. Then message again from the customer phone: the bot must stay silent. If it still answers, WAHA's `source` field is not `app` for phone-typed messages on your engine. Look at `docker compose logs waha` or the dashboard Event Monitor for a `message.any` event and tell the next session what `source` it carries.
5. Handoffs expire by themselves after `HANDOFF_TIMEOUT_HOURS` (default 12).

### Known flake (not a bug to fix tonight)
The conversation evals showed an occasional (~1 in 5 runs) reply in Arabic to an English customer in the `gift_for_mum` scenario. A prompt rule exists; the model (gpt-5-mini) still drifts rarely.

### 006: Hybrid retrieval with pgvector (done tonight, nothing manual)
Already done and verified: the Postgres container now runs `pgvector/pgvector:0.8.7-pg17-trixie` (your data was backed up first and is intact), the 212 products are embedded (`python scripts/build_embeddings.py`; a second run embeds 0), and the app uses `RETRIEVER=hybrid`. Optional: `python scripts/eval_retrieval.py` prints hit@3 for keyword/vector/hybrid. If you ever add products, re-run `python scripts/build_embeddings.py` (it only embeds what changed). If pgvector or embeddings are unavailable the bot silently falls back to keyword search (logged as `retrieval_fallback`).

### 011: Returning customer (optional phone check)
Tested with fakes, Postgres integration tests and a real-LLM eval scenario. To see it on your phone, you need a session that really expires:
1. In `.env` set `SESSION_TTL_SECONDS=60`, restart the app, then chat from the second phone (e.g. `I love bold gold rings, show me one`, then `I like the first one`).
2. Wait 70 seconds, then send `hi`. Expect a short "welcome back" that mentions your gold taste and asks if it still fits.
3. Restore `SESSION_TTL_SECONDS=86400` and restart.
Note: `redis-cli FLUSHALL` between messages will NOT trigger "welcome back" (the conversation is reloaded from Postgres, by design from issue 004). It does keep the learned preferences. Check the stored profile with:
```bash
docker compose exec postgres psql -U okhtein -d okhtein -c "select chat_id, profile from customers where profile is not null"
```

### 012: Load test (nothing manual; optional re-run)
Done and measured overnight (results in `docs/load-test-results.md`): webhook p95 **23 ms**, 0 failures at 100 simulated customers; 160/160 bursts got exactly one reply; 10 real-LLM conversations ran without errors, retries or fallbacks (replies took 20-40 s, all LLM time). To re-run: `python scripts/run_load_test.py` (isolated app on port 8001, cleans up after itself). Add nothing to `.env`; load mode is off by default (`LOAD_TEST_MODE=false`) and is refused when `ENVIRONMENT=production`.
