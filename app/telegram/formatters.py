"""Telegram HTML formatting helpers."""

from __future__ import annotations

from html import escape, unescape
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from app.telegram.models import (
    TELEGRAM_CAPTION_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    TELEGRAM_SAFE_MESSAGE_LIMIT,
)


def format_digest_message(
    items: Sequence[Mapping[str, Any] | Any],
    *,
    title: str = "Daily AI Technology Digest",
) -> str:
    """Format digest items as Telegram-compatible HTML."""

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
