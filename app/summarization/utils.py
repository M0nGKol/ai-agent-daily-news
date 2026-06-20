"""Utility helpers shared by summarization modules."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any


def extract_json_object(raw_text: str) -> str:
    """Extract the first JSON object from model text."""

    stripped = raw_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", raw_text, 0)
    return stripped[start : end + 1]


def coerce_score(value: Any, *, default: float) -> float:
    """Coerce a model-provided confidence score into the 0-1 range."""

    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def confidence_category(score: float) -> str:
    """Return a display category for a confidence score."""

    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def normalize_authors(value: Any) -> tuple[str, ...]:
    """Normalize authors from a string, sequence, or scalar value."""

    if value is None:
        return ()
    if isinstance(value, str):
        parts = re.split(r",| and ", value)
        return tuple(clean_text(part) for part in parts if clean_text(part))
    if isinstance(value, Sequence):
        return tuple(clean_text(author) for author in value if clean_text(author))
    return (clean_text(value),) if clean_text(value) else ()


def normalize_published_at(value: Any) -> str | None:
    """Normalize published_at values to string form for prompts."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return clean_text(value) or None


def read_config_value(config: Mapping[str, Any] | object | None, field_name: str) -> Any:
    """Read an uppercase or lowercase config value from a mapping/object."""

    if config is None:
        return None
    return read_field(config, field_name) or read_field(config, field_name.lower())


def read_field(item: Mapping[str, Any] | object, field_name: str) -> Any:
    """Read a field from a mapping or object."""

    if isinstance(item, Mapping):
        return item.get(field_name)
    return getattr(item, field_name, None)


def clean_text(value: Any) -> str:
    """Clean HTML-ish model/source text into compact plain text."""

    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
