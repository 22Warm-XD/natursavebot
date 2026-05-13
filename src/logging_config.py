from __future__ import annotations

import logging
import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"\b(bot_token|api_hash|api_key|password|session_string|authorization)\s*[:=]\s*['\"]?([^'\",\s]+)", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(r"(\d{6,}:[A-Za-z0-9_-]{20,})"),
    re.compile(r"([A-Za-z0-9_-]{80,}={0,2})"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in SECRET_PATTERNS:
            message = pattern.sub(lambda match: match.group(1) + "=<redacted>" if match.lastindex and match.lastindex > 1 else "<redacted>", message)
        record.msg = message
        record.args = ()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    root = logging.getLogger()
    redacting_filter = RedactingFilter()
    root.addFilter(redacting_filter)
    for handler in root.handlers:
        handler.addFilter(redacting_filter)
    for logger_name in ("telethon", "aiogram"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def log_safe_dict(data: dict[str, Any]) -> dict[str, Any]:
    secret_words = ("token", "hash", "key", "password", "session")
    return {key: "<redacted>" if any(word in key.lower() for word in secret_words) else value for key, value in data.items()}
