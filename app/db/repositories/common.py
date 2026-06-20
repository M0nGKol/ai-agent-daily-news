"""Shared repository helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import Engine

from app.db.base import Base
from app.db.session import create_db_engine, engine as default_engine

JsonPayload = Mapping[str, Any] | Sequence[Any]


def init_db(
    database_url: str | None = None,
    *,
    db_engine: Engine | None = None,
) -> Engine:
    """Create all database tables and return the engine used."""

    engine = db_engine or (default_engine if database_url is None else create_db_engine(database_url))
    Base.metadata.create_all(bind=engine)
    return engine


def content_hash(*, title: str, abstract: str | None, source_url: str) -> str:
    """Return a deterministic hash for source item de-duplication."""

    normalized = "\n".join(
        [
            title.strip().casefold(),
            (abstract or "").strip().casefold(),
            source_url.strip(),
        ]
    )
    return sha256(normalized.encode("utf-8")).hexdigest()


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Normalize datetimes to timezone-aware UTC."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_json_payload(payload: JsonPayload | None) -> dict[str, Any] | list[Any] | None:
    """Normalize a JSON payload to a SQLAlchemy-storable structure."""

    if payload is None:
        return None
    if isinstance(payload, Mapping):
        return dict(payload)
    return list(payload)


def require_non_empty(field_name: str, value: str | None) -> str:
    """Return stripped text or raise when a required field is empty."""

    cleaned = clean_optional_text(value)
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def clean_optional_text(value: str | None) -> str | None:
    """Return stripped text or None for empty optional text."""

    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
