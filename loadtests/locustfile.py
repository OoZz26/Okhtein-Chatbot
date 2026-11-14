"""Locust load test: simulated WhatsApp customers hitting the signed webhook.

Run it with the one-command runner (it starts an isolated app in load-test mode for you):
    python scripts/run_load_test.py

Two kinds of simulated customer:
  CustomerUser  a normal chatter: one message every few seconds (scenario A: capacity).
  BurstUser     sends 5 messages in under a second from a FRESH chat each time, then waits
                (scenario B: every burst must get exactly one reply; see check_bursts.py).
"""

import hashlib
import hmac
import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any

from locust import HttpUser, between, events, task

HMAC_KEY = os.environ.get("LOADTEST_HMAC_KEY", "loadtest-key")
BURSTS_FILE = Path(__file__).parent / "reports" / "bursts.json"
BURST_SIZE = 5
CUSTOMER_PREFIX = "299999"  # not an Egyptian prefix (20...), so cleanup can never touch a real customer
BURST_PREFIX = "299998"
MESSAGES = [
    "hi",
    "I want a black clutch",
    "something for a wedding",
    "show me earrings under 60000",
    "عايزة شنطة سهرة",
    "do you have a gift for my mum?",
    "can I return an item?",
]

bursts: list[dict[str, Any]] = []


def chat_id(prefix: str) -> str:
    return f"{prefix}{random.randrange(10**6):06d}@c.us"


def signed(chat: str, text: str) -> tuple[bytes, dict[str, str]]:
    """A realistic WAHA `message` event, signed with the webhook's HMAC-SHA512 like WAHA does."""
    body = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": f"false_{chat}_{uuid.uuid4().hex}",
            "from": chat,
            "fromMe": False,
            "body": text,
            "hasMedia": False,
            "_data": {"notifyName": "Load Tester"},
        },
    }
    raw = json.dumps(body).encode()
    signature = hmac.new(HMAC_KEY.encode(), raw, hashlib.sha512).hexdigest()
    return raw, {"Content-Type": "application/json", "X-Webhook-Hmac": signature}


class WebhookUser(HttpUser):
    abstract = True

    def post_message(self, chat: str, text: str) -> None:
        raw, headers = signed(chat, text)
        with self.client.post(
            "/webhook", data=raw, headers=headers, name="/webhook", catch_response=True
        ) as r:
            if r.status_code != 200 or r.json().get("status") != "accepted":
                r.failure(f"unexpected answer {r.status_code}: {r.text[:100]}")


class CustomerUser(WebhookUser):
    weight = 4
    wait_time = between(3, 8)

    def on_start(self) -> None:
        self.chat = chat_id(CUSTOMER_PREFIX)

    @task
    def say_something(self) -> None:
        self.post_message(self.chat, random.choice(MESSAGES))


class BurstUser(WebhookUser):
    weight = 1
    wait_time = between(12, 18)  # longer than the debounce quiet period + the fake LLM's 1-3 s

    @task
    def burst(self) -> None:
        chat = chat_id(BURST_PREFIX)  # a fresh customer per burst: one burst, one expected reply
        for number in range(BURST_SIZE):
            self.post_message(chat, f"burst message {number + 1}")
            time.sleep(random.uniform(0.05, 0.15))  # five messages in well under a second
        bursts.append({"chat_id": chat, "messages": BURST_SIZE, "at": time.time()})


@events.test_stop.add_listener
def write_bursts(**_: Any) -> None:
    BURSTS_FILE.parent.mkdir(exist_ok=True)
    BURSTS_FILE.write_text(json.dumps(bursts), encoding="utf-8")
