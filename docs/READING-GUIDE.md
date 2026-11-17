# Reading guide and decision log

How to read this project so you understand every part, and the decisions that brought it to where it is
today. Read it top to bottom once; after that, use it as a map.

## Part 1: how to read the project

### Step 1: the big picture (30 minutes)

1. [`README.md`](../README.md): what the bot does, the architecture diagram, the one-message sequence
   diagram, setup and configuration.
2. [`docs/issues/README.md`](issues/README.md): the 13 build slices in the order they were planned, and the
   engineering rules every slice follows (layers, SOLID, clean code).

After this you should be able to explain the four layers (`api → services → domain ← infra`) and why the
domain imports nothing from outside.

### Step 2: run it before reading code (20 minutes)

Seeing it work makes the code easier to follow.

```bash
.venv/Scripts/python -m pytest tests -q -p no:cacheprovider
```

Then start Docker and the app (README "Setup from zero") and talk to it over `/chat` with the admin key,
or from an allowed WhatsApp number. Watch `uvicorn.log` while you chat: every step logs one line.

### Step 3: the code, in the order a message travels (2 to 3 hours)

Read in this order. Each file has a one-line docstring at the top saying what it is for.

| # | File | What to look for |
|---|---|---|
| 1 | `app/domain/models.py`, `app/domain/ports.py` | The vocabulary: the data types and every interface the domain needs. Read these first; everything else uses them. |
| 2 | `app/api/webhook.py`, `app/infra/whatsapp/waha_mapper.py` | Signature check, mapping WAHA's JSON, answering at once and working in the background. |
| 3 | `app/services/incoming_message_service.py` | What gets ignored (groups, our own messages, numbers not allowed), dedupe, staff typing from the phone. |
| 4 | `app/services/debouncer.py` | How a burst becomes one reply, and the per-chat lock. The hardest file; read its tests too. |
| 5 | `app/services/reply_service.py` | Typing indicator, and why a failure never means silence. |
| 6 | `app/services/chat_service.py` | The heart: the order of every step for one reply. |
| 7 | `app/domain/discovery.py` | Stages, the 5-question checklist, "answer first", no repeated products. Rules enforced in code. |
| 8 | `app/domain/agent/sales_agent.py` and `app/domain/agent/prompts/system_v4.md` | How the prompt is built, the tool loop, the strict JSON reply, and how the output is validated. |
| 9 | `app/domain/tools/search_products.py`, `app/domain/retrieval/*` | Keyword, vector and hybrid search, and the fallback when vectors fail. |
| 10 | `app/domain/llm/fallback_chain.py`, `app/infra/llm/openai_provider.py` | Retries, OpenAI then OpenRouter, transient vs permanent errors. |
| 11 | `app/services/reply_sender.py`, `app/domain/bubbles.py`, `app/domain/reply_style.py` | How a reply is made to look human: bubbles, typing pauses, photo cards, no dashes or lists. |
| 12 | `app/domain/handoff.py`, `app/services/handoff_service.py` | The bot/person state machine and every way a chat changes hands. |
| 13 | `app/services/memory_service.py`, `app/services/returning_customer_service.py` | Short-term memory (Redis) vs the record (Postgres), and remembering people between visits. |
| 14 | `app/infra/**` | The adapters. Short; skim them to see each Redis pattern and each table. |
| 15 | `app/bootstrap.py` | Read last: now every class it wires is familiar. |

### Step 4: the tests as the specification (1 hour)

The tests describe the behaviour in plain sentences. Start with:

- `tests/fakes.py`: the in-memory stand-ins for every port, which is why the suite needs no Docker.
- `tests/unit/test_debouncer.py`, `test_discovery.py`, `test_handoff.py`, `test_chat_service*.py`.
- `tests/evals/`: the 21 scripted customers and the LLM judge that scores friendliness.

### Step 5: the history of each part (as deep as you want)

Every slice has an issue (what and why), a build prompt, and a commit. To see exactly what a slice added:

```bash
git log --reverse --oneline
```

```bash
git show --stat <commit>
```

Results worth reading: `docs/issues/006-hybrid-retrieval.md` (search accuracy per strategy),
`docs/load-test-results.md` (capacity), `docs/eval-report-latest.md` (conversation scores).

## Part 2: the decisions that led here

Listed in the order they were made. Each one says what was decided, why, and what it caused later.

### Foundations

| Decision | Why | What it led to |
|---|---|---|
| **Vertical slices (tracer bullets)** instead of building layer by layer | A thin end-to-end bot existed after slice 003 (about an hour). Every later slice was demoable on its own. | 13 slices, each with an issue, a prompt and a commit. Easy to review one at a time. |
| **Ports and adapters** with one composition root | Business rules must not depend on WhatsApp, OpenAI or a database, so they can be tested and swapped. | The whole suite runs on fakes in seconds; changing gateway or model is one adapter. A test enforces the domain imports nothing outside. |
| **Python app native, infrastructure in Docker** with named volumes | Fast reload while developing; the project sits on a Windows drive where bind mounts are slow. | `docker-compose.yml` runs Redis, Postgres and WAHA only. |
| **All settings in one typed object** | No hidden `os.getenv` calls; every tunable is documented and validated. | `app/core/config.py` and `.env.example`. |

### The tracer bullets (001 to 003)

| Decision | Why | What it led to |
|---|---|---|
| **HTTP `/chat` before WhatsApp** | Prove agent, search and links work without a phone. | `/chat` stayed as the demo and smoke-test door (now behind the admin key). |
| **Links are built by code from product handles, never written by the model** | Models invent URLs. A wrong link to a luxury product is worse than no link. | The agent strips URLs from replies and drops unknown handles. |
| **WAHA** (self-hosted WhatsApp Web) instead of the official Cloud API | Works with an existing number today, no Meta approval. | Ban risk accepted, so: an allowlist while testing, a global send rate limit, a signed webhook. The Cloud API is the production alternative. |
| **Acknowledge the webhook at once, work in the background** | WAHA retries slow webhooks, which causes duplicate replies. | Idempotency on message ids, and background services that log instead of raising. |

### Making it a conversation (004, 005, 011)

| Decision | Why | What it led to |
|---|---|---|
| **Two-tier memory: Redis for recent turns, Postgres as the record** | Every turn needs the last 20 messages fast; the history must survive a Redis flush and stay for staff. | `MemoryService` reads Redis first and rebuilds from Postgres on a miss. |
| **A persona ("Nour") and friendliness measured, not just prompted** | Friendliness is the client's top requirement. A prompt alone can't prove it. | The eval suite: scripted customers, hard rules checked in code, warmth scored by an LLM judge (target 4.0 or more). |
| **Discovery rules in code, not only in the prompt** | The model recommended too early and asked too many questions. | `DiscoveryPolicy`: stages, question limits, profile slots, enforced every turn. |
| **Remember returning customers** with a short LLM summary that never blocks a reply | "Welcome back" is part of the warmth; a slow summary must not delay the first answer. | Profile in `customers.profile` (JSONB), summary waits at most 3 s and finishes in the background. |

### Better answers (006, 007)

| Decision | Why | What it led to |
|---|---|---|
| **Hybrid search with pgvector**, keyword search as a fallback | Keyword search found 60% of the right products in the top 3; vector and hybrid found 84%, and handle Arabic and descriptions. | `Retriever` strategy chosen in config; `FallbackRetriever` keeps search working if embeddings fail. |
| **Embed only what changed**, using a content hash | Re-embedding the catalog on every start costs money and time. | `EmbeddingIndexer`. |
| **Store facts in an editable file** (`data/knowledge.md`) | The owner changes return policy or hours without a deploy; the bot must not guess unknown facts. | The file is re-read when it changes; unknown things get "a team member will confirm". |

### Feeling human and staying up (008, 009, 010, 012)

| Decision | Why | What it led to |
|---|---|---|
| **Debounce bursts and lock each chat** | People text in fragments; the bot answered each one, out of order. | One reply per burst, never two replies at once, with lock renewal for slow replies. |
| **Bubbles, typing pauses and photo cards** | A wall of text with links reads like a bot. | `ReplySender` and `ProductCardFactory`. |
| **LLM fallback chain** with retries; a holding message if everything fails | One provider outage must not silence every customer. | OpenAI first, OpenRouter second; failed chats are flagged in `follow_ups`. |
| **Human handoff** as two fields in the agent's JSON reply, not a tool | Tools are shared across chats and stateless; a tool would need hidden per-turn state. Same result, one fewer LLM call. | A two-state machine; staff typing from the phone also takes over; admin release and a 12 h auto release. |
| **Load test with a fake LLM** | A real model would measure OpenAI, cost money and hit rate limits before our code is stressed. | 100 simulated customers, 0 failures, webhook p95 23 ms; a separate 10-chat smoke test on the real model. |

### After the first build (from real chats)

| Decision | Why | What it led to |
|---|---|---|
| **Never leave a customer without a reply** (post-build review) | Postgres or Redis errors, or a failed "mark as seen", could drop a reply silently. | Holding message on any unexpected error; lock renewal; pick up messages that arrived during a reply. |
| **English only for now** (prompt v3) | Keep quality high in one language first; Arabic and Franco are still understood. | Arabic messages get a warm English reply. The bilingual prompt stays available. |
| **Speed: gpt-5.4-mini, no extra reasoning, at most 2 search rounds, searches in parallel** | Replies took 37 to 48 s. | Replies now take 1 to 5 s. |
| **No repeated products** | Customers saw the same bag again when asking for more. | The session remembers shown products; search marks them; a card is never sent twice. |
| **The rule for each reply goes after the customer's message** | The model ignored rules buried deep in the prompt. | `SalesAgent` adds a "Rule for this reply" last. |
| **Connect first, answer their question first** (detected in code) | Opening with a sales question felt pushy; ignoring a direct price question felt rude. | `asks_us_something` gates the "answer first" rule, so a plain need still goes through discovery. |
| **A casual texting voice, cleaned in code** | Replies read like catalog entries. The model kept adding dashes, lists and Arabic words. | Prompt v4 persona, plus `reply_style.py` removes dashes, list markers and Arabic words. |
| **Senior review before GitHub** | The repo was about to be shared. | `/chat` behind the admin key, no real numbers in docs or tests, no error details to callers, background failures logged, duplicated code removed. |

## Part 3: what is still open

- Real test number in old commits: rewrite history before the first public push, or keep the repo private.
- Background work runs inside the app process: a restart mid-burst leaves messages waiting until the customer
  writes again.
- No migration tool yet (Alembic).
- A vague Arabic first message sometimes gets products instead of a question (about 1 run in 3).
- No CI pipeline yet: ruff, mypy and pytest run locally only.
