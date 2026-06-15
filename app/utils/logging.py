"""Logging helpers with basic redaction for sensitive values."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"telegram_bot_token|llm_api_key|semantic_scholar_api_key|"
    r"api[_-]?key|access[_-]?token|bot[_-]?token|password|secret|token"
    r")\b(\s*[:=]\s*)([^\s,;]+)"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*(?:bearer|bot)?\s+)([^\s,;]+)"
)
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|key)=)([^&\s]+)"
)


def redact_secrets(value: Any, extra_values: Iterable[str] | None = None) -> str:
    """Return text with common token, key, and authorization values redacted."""

    text = str(value)
    text = _SENSITIVE_ASSIGNMENT_RE.sub(rf"\1\2{REDACTED}", text)
    text = _AUTH_HEADER_RE.sub(rf"\1{REDACTED}", text)
    text = _QUERY_SECRET_RE.sub(rf"\1{REDACTED}", text)

    for secret in extra_values or ():
        if secret:
            text = text.replace(str(secret), REDACTED)

    return text


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets before records are emitted."""

    def __init__(self, extra_values: Iterable[str] | None = None) -> None:
        super().__init__()
        self._extra_values = tuple(value for value in extra_values or () if value)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.getMessage(), self._extra_values)
        record.args = ()
        return True


def configure_logging(
    level: int | str = logging.INFO,
    extra_secret_values: Iterable[str] | None = None,
) -> None:
    """Configure application logging with a redaction filter on console output."""

    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter(extra_secret_values))
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
