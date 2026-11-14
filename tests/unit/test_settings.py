from pathlib import Path

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # so a developer's real .env is not picked up
    get_settings.cache_clear()


def test_defaults_match_the_agreed_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("HISTORY_LIMIT", "REDIS_HOST"):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.session_ttl_seconds == 24 * 60 * 60
    assert s.history_limit == 20
    assert s.max_discovery_questions == 3
    assert s.redis_url == "redis://localhost:6379/0"


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HISTORY_LIMIT", "5")
    monkeypatch.setenv("REDIS_HOST", "cache")
    s = Settings()
    assert s.history_limit == 5
    assert s.redis_url == "redis://cache:6379/0"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
