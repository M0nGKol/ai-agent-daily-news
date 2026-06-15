"""Telegram delivery helpers for the daily AI technology digest."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape, unescape
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from app.config import get_settings


TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_SAFE_MESSAGE_LIMIT = 3900
TELEGRAM_CAPTION_LIMIT = 1024


class TelegramConfigurationError(RuntimeError):
    """Raised when Telegram delivery is not configured correctly."""


@dataclass(frozen=True)
class TelegramDeliveryResult:
    """Structured result for a single Telegram sendMessage request."""

    ok: bool
    message_index: int
    total_messages: int
    character_count: int
    telegram_message_id: int | None = None
    status_code: int | None = None
    error: str | None = None
    dry_run: bool = False


def format_digest_message(
    items: Sequence[Mapping[str, Any] | Any],
    *,
    title: str = "Daily AI Technology Digest",
) -> str:
    """Format digest items as Telegram-compatible HTML.

    Each item must include a non-empty ``source_url``. Text values are escaped so
    that digest content cannot accidentally break Telegram's HTML parse mode.
    """

    escaped_title = escape(title.strip() or "Daily AI Technology Digest")
    lines = [f"<b>{escaped_title}</b>", f"{len(items)} curated AI update(s)."]

    for index, item in enumerate(items, start=1):
        lines.append("")
        lines.append(format_digest_item_card(item, index=index, total=len(items)))

    return "\n".join(lines)


def format_digest_header(
    *,
    title: str = "Daily AI Technology Digest",
    item_count: int,
) -> str:
    """Format a compact digest header message."""
    escaped_title = escape(title.strip() or "Daily AI Technology Digest")
    return (
        f"<b>{escaped_title}</b>\n"
        f"Top {item_count} AI news and research update(s) from multiple sources."
    )


def format_digest_item_card(
    item: Mapping[str, Any] | Any,
    *,
    index: int,
    total: int,
    max_chars: int = TELEGRAM_CAPTION_LIMIT,
) -> str:
    """Format one digest item as a compact Telegram card/caption."""
    source_url = _required_text_field(item, "source_url")
    item_title = _optional_text_field(item, "title", "Untitled")
    summary = _ellipsize(_optional_text_field(item, "summary"), 520)
    why_it_matters = _ellipsize(_optional_text_field(item, "why_it_matters"), 220)
    category = _optional_text_field(item, "category") or _domain_label(source_url)

    lines = [
        f"<b>{index}/{total}. {escape(item_title)}</b>",
        f"<i>{escape(category)}</i>",
    ]
    if summary:
        lines.append(f"\n<b>Summary</b>\n{escape(summary)}")
    if why_it_matters:
        lines.append(f"\n<b>Why it matters</b>\n{escape(why_it_matters)}")
    lines.append(f"\n<a href=\"{escape(source_url, quote=True)}\">Read source</a>")

    card = "\n".join(lines)
    if len(card) <= max_chars:
        return card

    shorter_summary = _ellipsize(summary, 320)
    shorter_why = _ellipsize(why_it_matters, 140)
    compact_lines = [
        f"<b>{index}/{total}. {escape(_ellipsize(item_title, 140))}</b>",
        f"<i>{escape(category)}</i>",
    ]
    if shorter_summary:
        compact_lines.append(f"\n{escape(shorter_summary)}")
    if shorter_why:
        compact_lines.append(f"\n<b>Why:</b> {escape(shorter_why)}")
    compact_lines.append(f"\n<a href=\"{escape(source_url, quote=True)}\">Read source</a>")
    compact_card = "\n".join(compact_lines)
    if len(compact_card) <= max_chars:
        return compact_card

    return "\n".join(
        [
            f"<b>{index}/{total}. {escape(_ellipsize(item_title, 96))}</b>",
            f"<i>{escape(_ellipsize(category, 80))}</i>",
            f"\n<a href=\"{escape(source_url, quote=True)}\">Read source</a>",
        ]
    )


def split_telegram_message(
    message: str,
    *,
    max_chars: int = TELEGRAM_SAFE_MESSAGE_LIMIT,
) -> list[str]:
    """Split a formatted Telegram message into chunks below Telegram's limit."""

    if max_chars <= 0 or max_chars > TELEGRAM_MESSAGE_LIMIT:
        raise ValueError(
            f"max_chars must be between 1 and {TELEGRAM_MESSAGE_LIMIT}, got {max_chars}"
        )

    if len(message) <= max_chars:
        return [message]

    chunks: list[str] = []
    current = ""

    for block in _message_blocks(message):
        separator = "\n\n" if current else ""
        candidate = f"{current}{separator}{block}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(block) <= max_chars:
            current = block
            continue

        chunks.extend(_split_oversized_block(block, max_chars=max_chars))

    if current:
        chunks.append(current)

    return chunks


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
        character_count=len(message),
        telegram_message_id=telegram_message_id,
        status_code=response.status_code,
        error=error,
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


def _message_blocks(message: str) -> list[str]:
    return [block for block in message.split("\n\n") if block]


def _split_oversized_block(block: str, *, max_chars: int) -> list[str]:
    plain_block = _plain_text_from_known_html(block)
    chunks: list[str] = []
    current = ""

    for line in plain_block.splitlines():
        separator = "\n" if current else ""
        candidate = f"{current}{separator}{line}"
        if len(escape(candidate)) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(escape(line)) <= max_chars:
            current = line
            continue

        chunks.extend(_hard_split_plain_text(line, max_chars=max_chars))

    if current:
        chunks.append(current)

    return [escape(chunk) for chunk in chunks]


def _hard_split_plain_text(text: str, *, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""

    for character in text:
        candidate = f"{current}{character}"
        if len(escape(candidate)) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
        current = character

    if current:
        chunks.append(current)

    return chunks


def _plain_text_from_known_html(fragment: str) -> str:
    plain_fragment = fragment
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        plain_fragment = plain_fragment.replace(tag, "")
    return unescape(plain_fragment)


def _ellipsize(value: str, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max(0, max_chars - 1)].rstrip()}..."


def _domain_label(source_url: str) -> str:
    parsed = urlparse(source_url)
    host = parsed.netloc or source_url
    return host[4:] if host.startswith("www.") else host


def _required_text_field(item: Mapping[str, Any] | Any, field_name: str) -> str:
    value = _item_value(item, field_name)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"Digest item is missing required field: {field_name}")
    return text


def _optional_text_field(
    item: Mapping[str, Any] | Any,
    field_name: str,
    default: str = "",
) -> str:
    value = _item_value(item, field_name)
    if value is None:
        return default
    return str(value).strip()


def _item_value(item: Mapping[str, Any] | Any, field_name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field_name)
    return getattr(item, field_name, None)
