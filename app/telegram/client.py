"""Telegram Bot API client helpers."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import httpx

from app.config import get_settings
from app.telegram.formatters import (
    format_digest_header,
    format_digest_item_card,
    split_telegram_message,
)
from app.telegram.models import (
    TELEGRAM_API_BASE_URL,
    TELEGRAM_CAPTION_LIMIT,
    TelegramConfigurationError,
    TelegramDeliveryResult,
)


def send_digest_to_telegram(
    items: Sequence[Mapping[str, Any] | Any],
    *,
    title: str = "Daily AI Technology Digest",
    bot_token: str | None = None,
    chat_id: str | int | None = None,
    timeout_seconds: float | None = None,
    dry_run: bool = False,
    client: httpx.Client | None = None,
) -> list[TelegramDeliveryResult]:
    """Send a digest header plus one structured Telegram card per item."""

    prepared_items = list(items)
    if not prepared_items:
        return []

    total_messages = len(prepared_items) + 1
    if dry_run:
        return [
            TelegramDeliveryResult(
                ok=False,
                message_index=index,
                total_messages=total_messages,
                character_count=0,
                error="Dry run enabled; Telegram API was not called.",
                dry_run=True,
            )
            for index in range(1, total_messages + 1)
        ]

    resolved_bot_token, resolved_chat_id, timeout = _resolve_telegram_settings(
        bot_token=bot_token,
        chat_id=chat_id,
        timeout_seconds=timeout_seconds,
    )
    _validate_telegram_settings(
        bot_token=resolved_bot_token,
        chat_id=resolved_chat_id,
    )

    close_client = client is None
    http_client = client or httpx.Client(timeout=timeout)
    try:
        results = [
            _send_one_message(
                client=http_client,
                bot_token=resolved_bot_token,
                chat_id=resolved_chat_id,
                message=format_digest_header(
                    title=title,
                    item_count=len(prepared_items),
                ),
                message_index=1,
                total_messages=total_messages,
                disable_web_page_preview=True,
            )
        ]
        for index, item in enumerate(prepared_items, start=1):
            results.append(
                _send_one_digest_item(
                    client=http_client,
                    bot_token=resolved_bot_token,
                    chat_id=resolved_chat_id,
                    item=item,
                    item_index=index,
                    message_index=index + 1,
                    total_messages=total_messages,
                )
            )
        return results
    finally:
        if close_client:
            http_client.close()


def send_telegram_messages(
    messages: Sequence[str],
    *,
    bot_token: str | None = None,
    chat_id: str | int | None = None,
    timeout_seconds: float | None = None,
    dry_run: bool = False,
    client: httpx.Client | None = None,
) -> list[TelegramDeliveryResult]:
    """Send preformatted Telegram HTML messages and return one result per message."""

    prepared_messages = [
        chunk for message in messages for chunk in split_telegram_message(message)
    ]
    if not prepared_messages:
        return []

    if dry_run:
        return [
            TelegramDeliveryResult(
                ok=False,
                message_index=index,
                total_messages=len(prepared_messages),
                character_count=len(message),
                error="Dry run enabled; Telegram API was not called.",
                dry_run=True,
            )
            for index, message in enumerate(prepared_messages, start=1)
        ]

    resolved_bot_token, resolved_chat_id, timeout = _resolve_telegram_settings(
        bot_token=bot_token,
        chat_id=chat_id,
        timeout_seconds=timeout_seconds,
    )

    _validate_telegram_settings(
        bot_token=resolved_bot_token,
        chat_id=resolved_chat_id,
    )

    close_client = client is None
    http_client = client or httpx.Client(timeout=timeout)
    try:
        return [
            _send_one_message(
                client=http_client,
                bot_token=resolved_bot_token,
                chat_id=resolved_chat_id,
                message=message,
                message_index=index,
                total_messages=len(prepared_messages),
            )
            for index, message in enumerate(prepared_messages, start=1)
        ]
    finally:
        if close_client:
            http_client.close()


def _send_one_message(
    *,
    client: httpx.Client,
    bot_token: str,
    chat_id: str,
    message: str,
    message_index: int,
    total_messages: int,
    disable_web_page_preview: bool = True,
) -> TelegramDeliveryResult:
    endpoint = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_web_page_preview,
    }

    try:
        response = client.post(endpoint, json=payload)
    except httpx.HTTPError as exc:
        return TelegramDeliveryResult(
            ok=False,
            message_index=message_index,
            total_messages=total_messages,
            character_count=len(message),
            error=f"Telegram API request failed: {exc.__class__.__name__}",
        )

    return _delivery_result_from_response(
        response=response,
        message_index=message_index,
        total_messages=total_messages,
        character_count=len(message),
    )


def _send_one_digest_item(
    *,
    client: httpx.Client,
    bot_token: str,
    chat_id: str,
    item: Mapping[str, Any] | Any,
    item_index: int,
    message_index: int,
    total_messages: int,
) -> TelegramDeliveryResult:
    card = format_digest_item_card(item, index=item_index, total=total_messages - 1)
    image_url = _optional_text_field(item, "image_url")
    if image_url:
        photo_result = _send_one_photo(
            client=client,
            bot_token=bot_token,
            chat_id=chat_id,
            photo_url=image_url,
            caption=card,
            message_index=message_index,
            total_messages=total_messages,
        )
        if photo_result.ok:
            return photo_result

    return _send_one_message(
        client=client,
        bot_token=bot_token,
        chat_id=chat_id,
        message=card,
        message_index=message_index,
        total_messages=total_messages,
        disable_web_page_preview=False,
    )


def _send_one_photo(
    *,
    client: httpx.Client,
    bot_token: str,
    chat_id: str,
    photo_url: str,
    caption: str,
    message_index: int,
    total_messages: int,
) -> TelegramDeliveryResult:
    endpoint = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption[:TELEGRAM_CAPTION_LIMIT],
        "parse_mode": "HTML",
    }

    try:
        response = client.post(endpoint, json=payload)
    except httpx.HTTPError as exc:
        return TelegramDeliveryResult(
            ok=False,
            message_index=message_index,
            total_messages=total_messages,
            character_count=len(caption),
            error=f"Telegram API photo request failed: {exc.__class__.__name__}",
        )

    return _delivery_result_from_response(
        response=response,
        message_index=message_index,
        total_messages=total_messages,
        character_count=len(caption),
    )


def _delivery_result_from_response(
    *,
    response: httpx.Response,
    message_index: int,
    total_messages: int,
    character_count: int,
) -> TelegramDeliveryResult:
    telegram_message_id: int | None = None
    error: str | None = None
    ok = response.status_code < 400

    try:
        body = response.json()
    except ValueError:
        body = {}
        if ok:
            error = "Telegram API returned a non-JSON response."
            ok = False

    if isinstance(body, dict):
        ok = bool(body.get("ok", ok))
        result = body.get("result")
        if isinstance(result, dict):
            message_id = result.get("message_id")
            if isinstance(message_id, int):
                telegram_message_id = message_id
        if not ok:
            description = body.get("description")
            error = (
                str(description)
                if description
                else f"Telegram API returned HTTP {response.status_code}."
            )
    else:
        error = (
            "Telegram API returned an unexpected JSON response."
            if ok
            else f"Telegram API returned HTTP {response.status_code}."
        )
        ok = False

    return TelegramDeliveryResult(
        ok=ok,
        message_index=message_index,
        total_messages=total_messages,
        character_count=character_count,
        telegram_message_id=telegram_message_id,
        status_code=response.status_code,
        error=error,
    )


def _validate_telegram_settings(*, bot_token: str | None, chat_id: str) -> None:
    if not bot_token or not bot_token.strip():
        raise TelegramConfigurationError(
            "TELEGRAM_BOT_TOKEN is required for delivery."
        )
    if not chat_id:
        raise TelegramConfigurationError("TELEGRAM_CHAT_ID is required for delivery.")


def _resolve_telegram_settings(
    *,
    bot_token: str | None,
    chat_id: str | int | None,
    timeout_seconds: float | None,
) -> tuple[str | None, str, float]:
    settings = get_settings()
    resolved_bot_token = (
        bot_token if bot_token is not None else settings.telegram_bot_token
    )
    resolved_chat_id_value = (
        chat_id if chat_id is not None else settings.telegram_chat_id
    )
    resolved_chat_id = (
        "" if resolved_chat_id_value is None else str(resolved_chat_id_value).strip()
    )
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(settings.http_timeout_seconds)
    )

    if timeout <= 0:
        raise TelegramConfigurationError("HTTP_TIMEOUT_SECONDS must be positive.")

    return resolved_bot_token, resolved_chat_id, timeout


def _optional_text_field(
    item: Mapping[str, Any] | Any,
    field_name: str,
    default: str = "",
) -> str:
    value = item.get(field_name) if isinstance(item, Mapping) else getattr(item, field_name, None)
    if value is None:
        return default
    return str(value).strip()
