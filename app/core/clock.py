"""The default clock. Every class that needs the time takes a `clock` argument, so tests inject their own."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
