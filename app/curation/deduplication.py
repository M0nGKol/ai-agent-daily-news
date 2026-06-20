"""Pure deduplication helpers for collected digest items."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DeduplicationKey = tuple[str, str]

_TEXT_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")
_MULTIPLE_SLASH_RE = re.compile(r"/+")
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "ref_src",
    "spm",
}


def item_value(item: Any, field_name: str, default: Any = None) -> Any:
    """Read a field from a dict-like, dataclass, Pydantic, or ORM-style item."""
    if isinstance(item, Mapping):
        return item.get(field_name, default)

    value = getattr(item, field_name, default)
    return default if callable(value) else value


def normalize_text(value: Any) -> str:
    """Normalize text for matching without changing the original item."""
    if value is None:
        return ""

    text = str(value).casefold()
    text = _TEXT_SEPARATOR_RE.sub(" ", text)
    return " ".join(text.split())


def normalize_title(title: Any) -> str:
    """Normalize a title into a stable key for duplicate detection."""
    return normalize_text(title)


def normalize_url(url: Any) -> str:
    """Normalize a source URL for deduplication.

    The normalizer removes fragments and common tracking parameters, lowercases
    scheme/host, collapses repeated path slashes, and keeps meaningful query
    parameters in sorted order.
    """
    if url is None:
        return ""

    raw_url = str(url).strip()
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    if not parsed.scheme and not parsed.netloc and "." in parsed.path.split("/")[0]:
        parsed = urlparse(f"https://{raw_url}")

    scheme = parsed.scheme.casefold()
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]

    path = _MULTIPLE_SLASH_RE.sub("/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_param(key)
    ]
    query = urlencode(sorted(query_pairs))

    return urlunparse((scheme, host, path, "", query, ""))


def content_hash(item: Any) -> str:
    """Return an existing or computed content hash for an item."""
    existing_hash = normalize_text(item_value(item, "content_hash", ""))
    if existing_hash:
        return existing_hash

    title = normalize_text(item_value(item, "title", ""))
    abstract = normalize_text(item_value(item, "abstract", ""))
    content = " ".join(part for part in (title, abstract) if part)
    if not content:
        return ""

    return sha256(content.encode("utf-8")).hexdigest()


def deduplication_keys(item: Any) -> list[DeduplicationKey]:
    """Build URL, title, and content-hash keys for one item."""
    keys: list[DeduplicationKey] = []

    url_key = normalize_url(item_value(item, "source_url", ""))
    if url_key:
        keys.append(("url", url_key))

    title_key = normalize_title(item_value(item, "title", ""))
    if title_key:
        keys.append(("title", title_key))

    hash_key = content_hash(item)
    if hash_key:
        keys.append(("content_hash", hash_key))

    return keys


def deduplicate_items(items: Iterable[Any]) -> list[Any]:
    """Return items with duplicate URLs, titles, or content hashes removed.

    The first item for a seen deduplication key is kept. Items without usable
    deduplication keys are retained because dropping them would hide data.
    """
    seen_keys: set[DeduplicationKey] = set()
    unique_items: list[Any] = []

    for item in items:
        keys = deduplication_keys(item)
        if keys and any(key in seen_keys for key in keys):
            continue

        unique_items.append(item)
        seen_keys.update(keys)

    return unique_items


def _is_tracking_query_param(param_name: str) -> bool:
    normalized = param_name.casefold()
    return normalized in _TRACKING_QUERY_PARAMS or normalized.startswith(
        _TRACKING_QUERY_PREFIXES
    )
