# 001 — Project foundation (prefactor)

**Status:** ✅ Done · **Estimate:** 20 min

## What to build

The empty-but-clean foundation every slice builds on. After this issue the repository has the
agreed layered package structure (api / services / domain / infra / core), quality tooling that
enforces clean code (ruff, mypy, pytest), one typed configuration object loaded from `.env`, and
the three infrastructure services — Postgres, Redis and WAHA — running in Docker and proven
reachable by a single health-check command.

The early prototype files in `app/` and the old `requirements.txt` predate the agreed design and
are removed. The project becomes a git repository. No business logic yet.

Decisions that apply from here on:
- Python 3.11+, installed as an editable package with dev extras.
- Postgres 17, Redis 7 and a pinned WAHA image, each with a health check and a **named volume**
  (the project lives on a Windows drive; bind mounts into Linux containers are slow).
- Nothing reads environment variables except the settings object; behaviour defaults live there
  (session TTL 24h, short-term history 20 messages, max 3 discovery questions, debounce seconds).
- Our Python app runs natively during development; only infrastructure runs in Docker.

## Acceptance criteria

- [x] `docker compose up -d` → all three services report **healthy**
- [x] The infra health-check command prints ✅/❌ for Postgres, Redis and WAHA and exits non-zero if any fail
- [x] `docker compose down` + `up` keeps Postgres data and the WAHA session (volumes survive)
- [x] `ruff check`, `ruff format --check`, `mypy app` and `pytest` all pass
- [x] A unit test proves settings load defaults and can be overridden by environment variables
- [x] `.env` is git-ignored; `.env.example` documents every setting and contains no real secret
- [x] Prototype files removed; layered package skeleton exists, each package with a one-line docstring saying what belongs there
- [x] Repository initialised with git and a first commit

## Blocked by

None - can start immediately
