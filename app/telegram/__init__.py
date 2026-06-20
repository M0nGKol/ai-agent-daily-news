"""Telegram delivery package."""

from app.telegram.client import send_digest_to_telegram, send_telegram_messages
from app.telegram.commands import (
    TelegramCommandPollResult,
    poll_telegram_commands_once,
    run_telegram_command_bot,
)
from app.telegram.formatters import (
    format_digest_header,
    format_digest_item_card,
    format_digest_message,
    split_telegram_message,
)
from app.telegram.models import (
    TELEGRAM_API_BASE_URL,
    TELEGRAM_CAPTION_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    TELEGRAM_SAFE_MESSAGE_LIMIT,
    TelegramConfigurationError,
    TelegramDeliveryResult,
)

__all__ = [
    "TELEGRAM_API_BASE_URL",
    "TELEGRAM_CAPTION_LIMIT",
    "TELEGRAM_MESSAGE_LIMIT",
    "TELEGRAM_SAFE_MESSAGE_LIMIT",
    "TelegramConfigurationError",
    "TelegramDeliveryResult",
    "TelegramCommandPollResult",
    "format_digest_header",
    "format_digest_item_card",
    "format_digest_message",
    "poll_telegram_commands_once",
    "run_telegram_command_bot",
    "send_digest_to_telegram",
    "send_telegram_messages",
    "split_telegram_message",
]
