"""Scenario B verification: every simulated burst must have received exactly ONE reply.

Reads the bursts Locust recorded and the sends the fake gateway recorded (GET /debug/sent).
Usage: python loadtests/check_bursts.py [--base-url http://127.0.0.1:8001]   (exit code 1 on any failure)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

BURSTS_FILE = Path(__file__).parent / "reports" / "bursts.json"


def main(base_url: str) -> int:
    bursts = json.loads(BURSTS_FILE.read_text(encoding="utf-8"))
    sends = httpx.get(f"{base_url}/debug/sent", timeout=30).json()
    replies = Counter(send["chat_id"] for send in sends if send["kind"] == "text")
    wrong = {b["chat_id"]: replies[b["chat_id"]] for b in bursts if replies[b["chat_id"]] != 1}
    print(f"bursts checked: {len(bursts)} (5 messages each)")
    print(f"bursts with exactly one reply: {len(bursts) - len(wrong)}")
    if wrong:
        print(f"❌ {len(wrong)} burst(s) with the wrong number of replies (chat -> replies): {wrong}")
        return 1
    print("✅ every burst got exactly one reply")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main(parser.parse_args().base_url))
