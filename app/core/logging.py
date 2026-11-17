"""Logging setup: key=value lines, with phone numbers and chat ids masked as a safety net."""

import logging
import re

from app.core.privacy import VISIBLE_DIGITS

# A run of 8+ digits (a phone number), optionally followed by a WhatsApp suffix such as "@c.us".
_SENSITIVE = re.compile(r"\b(\d{8,})(@(?:c\.us|lid|g\.us))?")


def mask_sensitive(text: str) -> str:
    """'201001234567@c.us' -> '…4567@c.us'. Keeps the last digits so a human can still correlate lines."""
    return _SENSITIVE.sub(lambda m: "…" + m.group(1)[-VISIBLE_DIGITS:] + (m.group(2) or ""), text)


class MaskSensitiveFilter(logging.Filter):
    """Masks phone numbers in every record, whoever logged it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive(record.getMessage())
        record.args = None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("time=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s")
    )
    handler.addFilter(MaskSensitiveFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
