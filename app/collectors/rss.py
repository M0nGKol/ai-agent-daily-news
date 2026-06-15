from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Any

import feedparser

from app.schemas import CollectedItem, clean_text, normalize_datetime


logger = logging.getLogger(__name__)

_IMG_SRC_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)


def collect_rss_items(
    feed_urls: Sequence[str],
    *,
    limit_per_feed: int = 20,
    parser: Callable[[str], Any] = feedparser.parse,
) -> list[CollectedItem]:
    """Collect entries from RSS or Atom feeds using feedparser."""
    if limit_per_feed <= 0:
        return []

    items: list[CollectedItem] = []
    for feed_url in [clean_text(url) for url in feed_urls if clean_text(url)]:
        try:
            parsed_feed = parser(feed_url)
        except Exception as exc:
            logger.warning("RSS collection failed for %s: %s", feed_url, exc)
            continue

        if _get(parsed_feed, "bozo", False):
            logger.warning("RSS feed parsed with warnings for %s", feed_url)

        feed = _get(parsed_feed, "feed", {}) or {}
        entries = _get(parsed_feed, "entries", []) or []
        source_name = clean_text(_get(feed, "title")) or feed_url

        for entry in entries[:limit_per_feed]:
            try:
                item = _entry_to_item(entry, source_name=source_name)
            except ValueError as exc:
                logger.debug("Skipping RSS entry without required fields: %s", exc)
                continue
            if item is not None:
                items.append(item)

    return items


def _entry_to_item(entry: Any, *, source_name: str) -> CollectedItem | None:
    source_url = _entry_source_url(entry)
    if not source_url:
        return None

    published_value = (
        _get(entry, "published_parsed")
        or _get(entry, "updated_parsed")
        or _get(entry, "published")
        or _get(entry, "updated")
    )

    return CollectedItem(
        source_type="rss",
        source_name=source_name,
        external_id=clean_text(_get(entry, "id")) or source_url,
        title=clean_text(_get(entry, "title")),
        abstract=clean_text(_get(entry, "summary")) or clean_text(_get(entry, "description")),
        authors=_entry_authors(entry),
        published_at=normalize_datetime(published_value),
        source_url=source_url,
        image_url=_entry_image_url(entry),
        raw_payload=_plain_dict(entry),
    )


def _entry_source_url(entry: Any) -> str:
    link = clean_text(_get(entry, "link"))
    if link:
        return link

    links = _get(entry, "links", []) or []
    for item in links:
        href = clean_text(_get(item, "href"))
        rel = clean_text(_get(item, "rel"))
        if href and rel == "alternate":
            return href

    for item in links:
        href = clean_text(_get(item, "href"))
        if href:
            return href

    entry_id = clean_text(_get(entry, "id"))
    if entry_id.startswith(("http://", "https://")):
        return entry_id

    return ""


def _entry_authors(entry: Any) -> list[str]:
    authors: list[str] = []
    for author in _get(entry, "authors", []) or []:
        name = clean_text(_get(author, "name")) or clean_text(_get(author, "author"))
        if name:
            authors.append(name)

    author = clean_text(_get(entry, "author"))
    if author and author not in authors:
        authors.append(author)

    return authors


def _entry_image_url(entry: Any) -> str | None:
    """Return the best image URL exposed by RSS/Atom metadata."""
    for field_name in ("media_thumbnail", "media_content"):
        image_url = _first_image_url(_get(entry, field_name, []) or [])
        if image_url:
            return image_url

    image = _get(entry, "image")
    if image:
        image_url = clean_text(_get(image, "href")) or clean_text(_get(image, "url"))
        if _is_http_url(image_url):
            return image_url

    links = _get(entry, "links", []) or []
    for item in links:
        href = clean_text(_get(item, "href"))
        mime_type = clean_text(_get(item, "type"))
        rel = clean_text(_get(item, "rel"))
        if _is_http_url(href) and (
            mime_type.startswith("image/") or rel in {"enclosure", "image"}
        ):
            return href

    for field_name in ("summary", "description", "content"):
        image_url = _image_from_htmlish_value(_get(entry, field_name))
        if image_url:
            return image_url

    return None


def _first_image_url(values: Sequence[Any]) -> str | None:
    for item in values:
        url = clean_text(_get(item, "url")) or clean_text(_get(item, "href"))
        mime_type = clean_text(_get(item, "type"))
        if _is_http_url(url) and (not mime_type or mime_type.startswith("image/")):
            return url
    return None


def _image_from_htmlish_value(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            image_url = _image_from_htmlish_value(_get(item, "value") or item)
            if image_url:
                return image_url
        return None

    text = str(value or "")
    match = _IMG_SRC_RE.search(text)
    if not match:
        return None

    image_url = clean_text(match.group(1))
    return image_url if _is_http_url(image_url) else None


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _get(value: Any, key: str, default: Any = None) -> Any:
    if hasattr(value, "get"):
        return value.get(key, default)
    return getattr(value, key, default)


def _plain_dict(value: Any) -> dict[str, Any]:
    if not hasattr(value, "items"):
        return {}
    return {str(key): _plain_value(item) for key, item in value.items()}


def _plain_value(value: Any) -> Any:
    if isinstance(value, time.struct_time):
        return tuple(value)
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _plain_value(item) for key, item in value.items()}
    return value
