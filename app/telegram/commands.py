"""Telegram command polling for manually triggering digest runs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.telegram.client import send_telegram_messages
from app.telegram.models import TELEGRAM_API_BASE_URL, TelegramConfigurationError


if TYPE_CHECKING:
    from app.pipelines.news_models import DailyDigestRunResult


logger = logging.getLogger(__name__)

DigestRunner = Callable[[Settings], "DailyDigestRunResult"]


@dataclass(frozen=True)
class TelegramCommand:
    """A normalized Telegram command message."""

    update_id: int
    chat_id: str
    user_id: str | None
    text: str


@dataclass(frozen=True)
class TelegramCommandPollResult:
    """Result from one Telegram getUpdates polling pass."""

    next_offset: int | None
    handled_commands: int = 0
    denied_commands: int = 0
    ignored_updates: int = 0
    errors: tuple[str, ...] = ()


def poll_telegram_commands_once(
    settings: Settings,
    *,
    offset: int | None = None,
    client: httpx.Client | None = None,
    digest_runner: DigestRunner | None = None,
) -> TelegramCommandPollResult:
    """Poll Telegram once and run the digest for authorized /digest commands."""

    bot_token = _required_bot_token(settings)
    close_client = client is None
    http_client = client or httpx.Client(
        timeout=settings.telegram_command_poll_timeout_seconds + 5
    )
    try:
        updates = _get_updates(
            http_client,
            bot_token=bot_token,
            offset=offset,
            timeout_seconds=settings.telegram_command_poll_timeout_seconds,
        )
        return _handle_updates(
            updates,
            settings=settings,
            client=http_client,
            digest_runner=digest_runner or _run_daily_digest,
        )
    finally:
        if close_client:
            http_client.close()


def run_telegram_command_bot(
    settings: Settings,
    *,
    listen: bool = True,
    poll_interval_seconds: float = 1.0,
    client: httpx.Client | None = None,
    digest_runner: DigestRunner | None = None,
) -> TelegramCommandPollResult:
    """Run the Telegram command bot once or as a long-polling worker."""

    offset: int | None = None
    last_result = TelegramCommandPollResult(next_offset=None)
    while True:
        last_result = poll_telegram_commands_once(
            settings,
            offset=offset,
            client=client,
            digest_runner=digest_runner or _run_daily_digest,
        )
        offset = last_result.next_offset
        if not listen:
            return last_result
        if poll_interval_seconds > 0:
            time.sleep(poll_interval_seconds)


def _get_updates(
    client: httpx.Client,
    *,
    bot_token: str,
    offset: int | None,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    endpoint = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/getUpdates"
    params: dict[str, Any] = {
        "timeout": timeout_seconds,
        "allowed_updates": '["message","channel_post"]',
    }
    if offset is not None:
        params["offset"] = offset

    try:
        response = client.get(endpoint, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Telegram command polling failed: %s", exc)
        return []

    if not isinstance(payload, dict) or not payload.get("ok"):
        return []
    updates = payload.get("result")
    return updates if isinstance(updates, list) else []


def _handle_updates(
    updates: list[dict[str, Any]],
    *,
    settings: Settings,
    client: httpx.Client,
    digest_runner: DigestRunner,
) -> TelegramCommandPollResult:
    next_offset: int | None = None
    handled_commands = 0
    denied_commands = 0
    ignored_updates = 0
    errors: list[str] = []

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            next_offset = max(next_offset or update_id + 1, update_id + 1)

        command = _command_from_update(update)
        if command is None:
            ignored_updates += 1
            continue
        if not _is_digest_command(command.text, settings.telegram_digest_command):
            ignored_updates += 1
            continue
        if not _is_allowed_command(command, settings):
            denied_commands += 1
            _reply(
                settings,
                client=client,
                chat_id=command.chat_id,
                message="This chat is not allowed to trigger the digest.",
            )
            continue

        _reply(
            settings,
            client=client,
            chat_id=command.chat_id,
            message="Starting the AI news digest now.",
        )
        try:
            result = digest_runner(settings)
        except Exception as exc:
            logger.exception("Digest command failed")
            errors.append(f"digest failed: {exc.__class__.__name__}")
            _reply(
                settings,
                client=client,
                chat_id=command.chat_id,
                message="Digest failed. Check the worker logs for details.",
            )
            continue

        handled_commands += 1
        _reply(
            settings,
            client=client,
            chat_id=command.chat_id,
            message=_digest_result_message(result),
        )

    return TelegramCommandPollResult(
        next_offset=next_offset,
        handled_commands=handled_commands,
        denied_commands=denied_commands,
        ignored_updates=ignored_updates,
        errors=tuple(errors),
    )


def _command_from_update(update: dict[str, Any]) -> TelegramCommand | None:
    message = update.get("message") or update.get("channel_post")
    if not isinstance(message, dict):
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip().startswith("/"):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None
    sender = message.get("from")
    user_id = (
        str(sender.get("id"))
        if isinstance(sender, dict) and sender.get("id") is not None
        else None
    )
    update_id = update.get("update_id")
    return TelegramCommand(
        update_id=update_id if isinstance(update_id, int) else 0,
        chat_id=str(chat["id"]),
        user_id=user_id,
        text=text.strip(),
    )


def _is_digest_command(text: str, configured_command: str) -> bool:
    command = configured_command.strip() or "/digest"
    first_token = text.split(maxsplit=1)[0]
    first_token = first_token.split("@", maxsplit=1)[0]
    return first_token.casefold() == command.casefold()


def _is_allowed_command(command: TelegramCommand, settings: Settings) -> bool:
    allowed_ids = _parse_allowed_ids(settings.telegram_command_allowed_ids)
    if allowed_ids:
        return command.chat_id in allowed_ids or command.user_id in allowed_ids

    target_chat_id = str(settings.telegram_chat_id or "").strip()
    return bool(target_chat_id and command.chat_id == target_chat_id)


def _parse_allowed_ids(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _reply(
    settings: Settings,
    *,
    client: httpx.Client,
    chat_id: str,
    message: str,
) -> None:
    try:
        send_telegram_messages(
            [message],
            bot_token=settings.telegram_bot_token,
            chat_id=chat_id,
            timeout_seconds=settings.http_timeout_seconds,
            client=client,
        )
    except TelegramConfigurationError:
        raise
    except Exception:
        logger.exception("Failed to send Telegram command reply")


def _digest_result_message(result: "DailyDigestRunResult") -> str:
    if result.delivery_succeeded:
        return f"Digest sent with {result.summarized_count} item(s)."
    if result.summarized_count == 0:
        return "Digest ran, but no publishable items were found."
    return "Digest ran, but Telegram delivery did not fully succeed."


def _required_bot_token(settings: Settings) -> str:
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        raise TelegramConfigurationError(
            "TELEGRAM_BOT_TOKEN is required for command polling."
        )
    return token


def _run_daily_digest(settings: Settings) -> "DailyDigestRunResult":
    from app.pipelines.news_digest import run_daily_digest

    return run_daily_digest(settings)
