"""Infrastructure health check: Postgres, Redis and WAHA must all be reachable.

Usage: python scripts/check_infra.py   (exit code 1 if anything is down)
"""

import asyncio
import sys
from collections.abc import Awaitable, Callable

import asyncpg
import httpx
import redis.asyncio as aioredis

from app.core.config import Settings, get_settings

CHECK_TIMEOUT_SECONDS = 5.0


async def check_postgres(s: Settings) -> None:
    conn = await asyncpg.connect(s.postgres_dsn, timeout=CHECK_TIMEOUT_SECONDS)
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()


async def check_redis(s: Settings) -> None:
    client = aioredis.from_url(s.redis_url, socket_timeout=CHECK_TIMEOUT_SECONDS)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_waha(s: Settings) -> None:
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as http:
        resp = await http.get(f"{s.waha_url}/api/sessions", headers={"X-Api-Key": s.waha_api_key})
        resp.raise_for_status()


async def run_check(name: str, check: Callable[[Settings], Awaitable[None]], s: Settings) -> bool:
    try:
        await check(s)
    except Exception as exc:  # report any failure, never crash the checker
        print(f"❌ {name}: {type(exc).__name__}: {exc}")
        return False
    print(f"✅ {name}")
    return True


async def main() -> int:
    s = get_settings()
    checks = [("Postgres", check_postgres), ("Redis", check_redis), ("WAHA", check_waha)]
    results = [await run_check(name, fn, s) for name, fn in checks]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows consoles default to cp1252
    sys.exit(asyncio.run(main()))
