"""Telegram delivery models and limits."""

from __future__ import annotations

from dataclasses import dataclass


TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_SAFE_MESSAGE_LIMIT = 3900
TELEGRAM_CAPTION_LIMIT = 1024


class TelegramConfigurationError(RuntimeError):
    """Raised when Telegram delivery is not configured correctly."""


@dataclass(frozen=True)
class TelegramDeliveryResult:
    """Structured result for a single Telegram API request."""

    ok: bool
    message_index: int
    total_messages: int
    character_count: int
    telegram_message_id: int | None = None
    status_code: int | None = None
    error: str | None = None
    dry_run: bool = False
