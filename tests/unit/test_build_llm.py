"""Provider order, skipping providers without keys, and rejecting bad configuration."""

import pytest

from app.bootstrap import build_llm
from app.core.config import Settings
from app.domain.errors import ConfigurationError


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "openai_api_key": "sk-test",
        "openrouter_api_key": "or-test",
        "_env_file": None,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def names(**overrides: object) -> list[str]:
    return [slot.name for slot in build_llm(settings(**overrides))._slots]


def test_default_order_is_openai_then_openrouter() -> None:
    assert names() == ["openai", "openrouter"]


def test_the_order_is_configurable() -> None:
    assert names(llm_provider_order="openrouter,openai") == ["openrouter", "openai"]


def test_a_provider_without_a_key_is_skipped() -> None:
    assert names(openrouter_api_key="") == ["openai"]


def test_timeouts_and_retries_come_from_settings() -> None:
    chain = build_llm(settings(llm_max_retries=5, llm_retry_base_delay_seconds=0.25))

    assert chain._max_retries == 5
    assert chain._base_delay == 0.25


def test_no_keys_at_all_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        build_llm(settings(openai_api_key="", openrouter_api_key=""))


def test_an_unknown_provider_name_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        build_llm(settings(llm_provider_order="openai,gemini"))
