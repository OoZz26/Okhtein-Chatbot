import logging

import pytest

from app.core.logging import MaskSensitiveFilter, mask_sensitive


def test_phone_numbers_and_chat_ids_are_masked() -> None:
    assert mask_sensitive("from 201001234567@c.us") == "from …4567@c.us"
    assert mask_sensitive("lid 12345678901234@lid") == "lid …1234@lid"
    assert mask_sensitive("call 01012345678 now") == "call …5678 now"


def test_short_numbers_and_normal_text_are_left_alone() -> None:
    text = "latency_ms=1234 attempts=2 price 55,000 EGP order 1234567"
    assert mask_sensitive(text) == text


def test_the_filter_masks_numbers_passed_as_log_arguments(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.masking")
    handler = logging.StreamHandler()
    records: list[str] = []
    handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
    handler.addFilter(MaskSensitiveFilter())
    logger.addHandler(handler)
    try:
        logger.warning("could not reply to %s", "201001234567@c.us")
    finally:
        logger.removeHandler(handler)

    assert records == ["could not reply to …4567@c.us"]
