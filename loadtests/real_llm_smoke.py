"""Scenario C: ~10 concurrent conversations through /chat against the REAL LLM (not a capacity test).

Shows what the fake-LLM tests cannot: real latency, rate limiting, retries and whether the fallback
provider was used. Costs a few cents. Does NOT touch WhatsApp (/chat only returns text).

Usage (the real app must be running with real keys):
    python loadtests/real_llm_smoke.py --base-url http://127.0.0.1:8000 --log uvicorn.log

The app's log (only the lines written during the run) is read to count retries, fallbacks and holds.
"""

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.infra.db.session import create_engine
from app.services.chat_service import HOLDING_MESSAGE

CONVERSATIONS = 10
CHAT_PREFIX = "299997"
SCRIPT = [
    "I'm looking for a gift for my mum, she loves gold",
    "Her birthday is next week and my budget is around 60000 EGP",
]
LOG_MARKERS = {
    "retried (429 or 5xx)": "llm_retry",
    "provider failed (fell back)": "llm_provider_failed",
    "answered by openrouter": "llm_call provider=openrouter",
    "holding message sent": "outcome=degraded",
    "semantic search fell back": "retrieval_fallback",
}


async def conversation(client: httpx.AsyncClient, number: int) -> list[tuple[float, int, bool]]:
    """One simulated customer: returns (seconds, HTTP status, was-it-the-holding-message) per message."""
    chat_id = f"{CHAT_PREFIX}{number:06d}@c.us"
    results = []
    for message in SCRIPT:
        started = time.perf_counter()
        response = await client.post("/chat", json={"chat_id": chat_id, "text": message})
        elapsed = time.perf_counter() - started
        reply = response.json().get("reply", "") if response.status_code == 200 else ""
        results.append((elapsed, response.status_code, reply == HOLDING_MESSAGE))
    return results


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


async def delete_fake_customers() -> None:
    s = get_settings()
    engine = create_engine(
        s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db
    )
    async with engine.begin() as connection:
        for table in ("messages", "customers", "follow_ups", "handoffs"):
            await connection.execute(
                text(f"DELETE FROM {table} WHERE chat_id LIKE :p"), {"p": f"{CHAT_PREFIX}%"}
            )
    await engine.dispose()


async def main(base_url: str, log_path: Path | None) -> int:
    log_start = log_path.stat().st_size if log_path and log_path.exists() else 0
    headers = {"X-Admin-Key": get_settings().admin_api_key}  # /chat is a team-only endpoint
    async with httpx.AsyncClient(base_url=base_url, timeout=180, headers=headers) as client:
        started = time.perf_counter()
        runs = await asyncio.gather(*(conversation(client, n) for n in range(CONVERSATIONS)))
        wall = time.perf_counter() - started
    await delete_fake_customers()
    flat = [item for run in runs for item in run]
    latencies = [seconds for seconds, _, _ in flat]
    p50, p95 = statistics.median(latencies), percentile(latencies, 0.95)
    errors = sum(1 for _, status, _ in flat if status != 200)
    held = sum(1 for *_, was_held in flat if was_held)
    total = len(flat)
    print(f"{CONVERSATIONS} conversations x {len(SCRIPT)} messages = {total} replies in {wall:.1f}s")
    print(f"latency per reply: p50 {p50:.1f}s  p95 {p95:.1f}s  max {max(latencies):.1f}s")
    print(f"HTTP errors: {errors}   holding messages: {held}")
    if log_path and log_path.exists():
        with log_path.open(encoding="utf-8", errors="replace") as file:
            file.seek(log_start)
            new_lines = file.read()
        for label, marker in LOG_MARKERS.items():
            print(f"  {label}: {new_lines.count(marker)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--log", type=Path, default=None, help="the running app's log file")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(asyncio.run(main(args.base_url, args.log)))
