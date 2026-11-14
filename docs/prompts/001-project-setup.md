Implement issue **001 — Project foundation** for the Okhtein WhatsApp bot.

First read `docs/prompts/_common.md` (shared rules) and `docs/issues/001-project-setup.md`.

Guidance:
- Look at the prototype files in `app/` and `requirements.txt` before deleting them; tell me if
  anything in them is worth carrying over (e.g. ideas for later slices), then remove them.
- `git init` with a `.gitignore` for `.env`, `.venv/`, caches, `__pycache__/`, `loadtests/reports/`.
- `pyproject.toml` (setuptools or hatchling), installable with `pip install -e ".[dev]"`.
  Runtime: fastapi, uvicorn[standard], pydantic, pydantic-settings, httpx, openai, numpy, redis,
  sqlalchemy[asyncio], asyncpg. Dev: pytest, pytest-asyncio, ruff, mypy, fakeredis, locust.
  Ruff: line length 110, rules E,F,I,B,UP,SIM,N. Mypy: strict for `app.domain` and `app.services`.
  Pytest: asyncio mode auto, test paths `tests/`.
- Package skeleton: `app/{core,domain,services,infra,api}` plus `infra/{llm,cache,db,whatsapp,catalog}`;
  `tests/{unit,integration,evals}`; `loadtests/`. Each `__init__.py` has a one-line docstring.
- `app/core/config.py`: `Settings` grouped by concern (store, llm, embeddings, redis, postgres,
  waha, behaviour) and `get_settings()` with `@lru_cache`.
- `docker-compose.yml`: `postgres:17`, `redis:7`, and WAHA (`devlikeapro/waha`, pin a recent
  tag — check the WAHA docs for the current one and its env var names for the API key and
  webhook). Health checks, named volumes, values from `.env`.
- `scripts/check_infra.py`: async; Postgres `SELECT 1`, Redis `PING`, WAHA sessions endpoint with
  the API key header. Prints ✅/❌ per service, exit code 1 on failure.
- Create `.env.example`; then ask me to copy it to `.env` and fill in my own secrets before
  you run the health check.

Demo at the end: `docker compose up -d`, `docker compose ps`, `python scripts/check_infra.py`,
and the full quality check.
