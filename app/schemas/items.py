from __future__ import annotations

import calendar
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def clean_text(value: Any) -> str:
    """Return a compact string with repeated whitespace collapsed."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def normalize_datetime(value: Any) -> datetime | None:
    """Normalize common API and RSS date values to timezone-aware UTC datetimes."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return _as_utc(value)

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    if isinstance(value, time.struct_time):
        return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)

    if isinstance(value, int) and 1 <= value <= 9999:
        return datetime(value, 1, 1, tzinfo=timezone.utc)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            return _as_utc(datetime.fromisoformat(iso_text))
        except ValueError:
            pass

        try:
            return _as_utc(parsedate_to_datetime(text))
        except (TypeError, ValueError, IndexError, OverflowError):
            return None

    return None


@dataclass(slots=True)
class CollectedItem:
    source_type: str
    source_name: str
    external_id: str
    title: str
    abstract: str
    authors: list[str]
    published_at: datetime | None
    source_url: str
    image_url: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_type = clean_text(self.source_type)
        self.source_name = clean_text(self.source_name)
        self.external_id = clean_text(self.external_id)
        self.title = clean_text(self.title)
        self.abstract = clean_text(self.abstract)
        self.authors = [clean_text(author) for author in self.authors if clean_text(author)]
        self.published_at = normalize_datetime(self.published_at)
        self.source_url = clean_text(self.source_url)
        self.image_url = clean_text(self.image_url) or None
        self.raw_payload = dict(self.raw_payload or {})

        if not self.source_url:
            raise ValueError("CollectedItem.source_url must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation for persistence or ranking."""
        return asdict(self)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
