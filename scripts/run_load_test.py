"""One command for scenarios A and B: capacity and burst correctness, with the LLM and WhatsApp faked.

    python scripts/run_load_test.py                       # 100 customers for 2 minutes
    python scripts/run_load_test.py --users 50 --time 1m

It starts an isolated copy of the app on port 8001 in load-test mode (fake LLM with 1-3 s latency, fake
WhatsApp gateway, Redis database 14), runs Locust headless, saves reports in loadtests/reports/, verifies
that every burst got exactly one reply, and deletes the fake customers it created.
"""

import argparse
import asyncio
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.infra.db.session import create_engine

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "loadtests" / "reports"
HMAC_KEY = "loadtest-key"
LOAD_TEST_REDIS_DB = 14
FAKE_CHAT_PREFIX = "2999"  # all simulated customers; never an Egyptian (20...) number
P95_TARGET_MS = 100
SETTLE_SECONDS = 10  # let the last bursts finish: debounce (1 s) + fake LLM (up to 3 s) + sending


def server_env(port: int) -> dict[str, str]:
    return {
        **os.environ,
        "LOAD_TEST_MODE": "true",
        "ENVIRONMENT": "development",
        "REDIS_DB": str(LOAD_TEST_REDIS_DB),
        "WAHA_WEBHOOK_HMAC_KEY": HMAC_KEY,
        "ALLOWED_NUMBERS": "",
        "DEBOUNCE_SECONDS": "1.0",  # a short quiet period keeps the test short
        "SEND_RATE_LIMIT_PER_MINUTE": "1000000",  # the real limit protects a real number; not under test here
        "TYPING_SECONDS_PER_CHAR": "0",
        "TYPING_MAX_DELAY_SECONDS": "0",
        "PYTHONIOENCODING": "utf-8",
    }


def wait_for_health(port: int, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.5)
    raise RuntimeError("the load-test app did not become healthy")


async def delete_fake_customers() -> None:
    s = get_settings()
    engine = create_engine(
        s.postgres_host, s.postgres_port, s.postgres_user, s.postgres_password, s.postgres_db
    )
    pattern = f"{FAKE_CHAT_PREFIX}%"
    async with engine.begin() as connection:
        for table in ("messages", "customers", "follow_ups", "handoffs"):
            await connection.execute(text(f"DELETE FROM {table} WHERE chat_id LIKE :p"), {"p": pattern})
    await engine.dispose()


def webhook_row() -> dict[str, str]:
    with (REPORTS / "a_stats.csv").open(encoding="utf-8") as file:
        return next(row for row in csv.DictReader(file) if row["Name"] == "/webhook")


def main(users: int, spawn_rate: int, duration: str, port: int) -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    log = (REPORTS / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=server_env(port),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_health(port)
        print(f"load-test app up on :{port}; running {users} simulated customers for {duration}...")
        locust = subprocess.run(
            [
                sys.executable, "-m", "locust", "-f", "loadtests/locustfile.py", "--headless",
                "-u", str(users), "-r", str(spawn_rate), "-t", duration, "--host", f"http://127.0.0.1:{port}",
                "--html", "loadtests/reports/a.html", "--csv", "loadtests/reports/a", "--only-summary",
            ],
            cwd=ROOT,
            env={**os.environ, "LOADTEST_HMAC_KEY": HMAC_KEY},
        )  # fmt: skip
        print(f"waiting {SETTLE_SECONDS}s for the last replies...")
        time.sleep(SETTLE_SECONDS)
        bursts = subprocess.run(
            [sys.executable, "loadtests/check_bursts.py", "--base-url", f"http://127.0.0.1:{port}"], cwd=ROOT
        )
    finally:
        server.terminate()
        server.wait(timeout=20)
        log.close()
        asyncio.run(delete_fake_customers())
    row = webhook_row()
    p50, p95, failures = float(row["50%"]), float(row["95%"]), int(row["Failure Count"])
    requests = row["Request Count"]
    print(
        f"\nscenario A: {requests} webhook requests, p50 {p50:.0f} ms, p95 {p95:.0f} ms, failures {failures}"
    )
    a_ok = p95 < P95_TARGET_MS and failures == 0
    print(f"{'✅' if a_ok else '❌'} target: p95 < {P95_TARGET_MS} ms and 0 failures")
    print("reports: loadtests/reports/a.html and a_stats.csv")
    return 0 if a_ok and locust.returncode == 0 and bursts.returncode == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--spawn-rate", type=int, default=10)
    parser.add_argument("--time", default="2m")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main(args.users, args.spawn_rate, args.time, args.port))
