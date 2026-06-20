"""Repository helpers for sources and collected source items."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Source, SourceItem
from app.db.repositories.common import (
    JsonPayload,
    clean_optional_text,
    content_hash as build_content_hash,
    normalize_datetime,
    normalize_json_payload,
    require_non_empty,
)


def get_or_create_source(
    db: Session,
    *,
    source_type: str,
    name: str,
    url: str | None = None,
    is_active: bool = True,
) -> Source:
    """Return an existing source by type/name, or create it."""

    clean_source_type = require_non_empty("source_type", source_type)
    clean_name = require_non_empty("name", name)
    clean_url = clean_optional_text(url)

    source = db.scalar(
        select(Source).where(
            Source.source_type == clean_source_type,
            Source.name == clean_name,
        )
    )
    if source:
        if clean_url and source.url != clean_url:
            source.url = clean_url
        source.is_active = is_active
        db.flush()
        return source

    source = Source(
        source_type=clean_source_type,
        name=clean_name,
        url=clean_url,
        is_active=is_active,
    )
    db.add(source)
    db.flush()
    return source


def upsert_source_item(
    db: Session,
    *,
    title: str,
    source_url: str,
    source: Source | None = None,
    source_id: int | None = None,
    source_type: str | None = None,
    source_name: str | None = None,
    source_homepage_url: str | None = None,
    external_id: str | None = None,
    abstract: str | None = None,
    authors: Sequence[str] | None = None,
    published_at: datetime | None = None,
    raw_payload: JsonPayload | None = None,
    content_hash: str | None = None,
) -> SourceItem:
    """Create or update a collected item, deduping by source/external ID or URL/hash."""

    clean_title = require_non_empty("title", title)
    clean_source_url = require_non_empty("source_url", source_url)
    clean_external_id = clean_optional_text(external_id)
    owner = _resolve_source(
        db,
        source=source,
        source_id=source_id,
        source_type=source_type,
        source_name=source_name,
        source_homepage_url=source_homepage_url,
    )
    clean_hash = clean_optional_text(content_hash) or build_content_hash(
        title=clean_title,
        abstract=abstract,
        source_url=clean_source_url,
    )

    item = _find_existing_source_item(
        db,
        source_id=owner.id,
        external_id=clean_external_id,
        content_hash=clean_hash,
        source_url=clean_source_url,
    )

    if item is None:
        item = SourceItem(
            source_id=owner.id,
            external_id=clean_external_id,
            title=clean_title,
            abstract=abstract,
            authors=list(authors or []),
            published_at=normalize_datetime(published_at),
            source_url=clean_source_url,
            content_hash=clean_hash,
            raw_payload=normalize_json_payload(raw_payload),
        )
        db.add(item)
    else:
        item.source_id = owner.id
        item.external_id = clean_external_id or item.external_id
        item.title = clean_title
        item.abstract = abstract
        item.authors = list(authors or [])
        item.published_at = normalize_datetime(published_at)
        item.source_url = clean_source_url
        item.content_hash = clean_hash
        item.raw_payload = normalize_json_payload(raw_payload)

    db.flush()
    return item


def list_recent_items(
    db: Session,
    *,
    limit: int = 50,
    since: datetime | None = None,
    source_id: int | None = None,
) -> list[SourceItem]:
    """List recently published or collected source items."""

    if limit < 1:
        raise ValueError("limit must be greater than zero")

    statement = select(SourceItem)
    if since is not None:
        normalized_since = normalize_datetime(since)
        statement = statement.where(
            or_(
                SourceItem.published_at >= normalized_since,
                and_(
                    SourceItem.published_at.is_(None),
                    SourceItem.created_at >= normalized_since,
                ),
            )
        )
    if source_id is not None:
        statement = statement.where(SourceItem.source_id == source_id)

    statement = statement.order_by(
        SourceItem.published_at.is_(None),
        SourceItem.published_at.desc(),
        SourceItem.created_at.desc(),
    ).limit(limit)
    return list(db.scalars(statement))


def _find_existing_source_item(
    db: Session,
    *,
    source_id: int,
    external_id: str | None,
    content_hash: str,
    source_url: str,
) -> SourceItem | None:
    if external_id:
        item = db.scalar(
            select(SourceItem).where(
                SourceItem.source_id == source_id,
                SourceItem.external_id == external_id,
            )
        )
        if item:
            return item

    return db.scalar(
        select(SourceItem)
        .where(SourceItem.source_url == source_url)
        .order_by(SourceItem.id)
    )


def _resolve_source(
    db: Session,
    *,
    source: Source | None,
    source_id: int | None,
    source_type: str | None,
    source_name: str | None,
    source_homepage_url: str | None,
) -> Source:
    if source is not None:
        return source
    if source_id is not None:
        resolved_source = db.get(Source, source_id)
        if resolved_source is None:
            raise ValueError(f"source_id {source_id} does not exist")
        return resolved_source
    if source_type and source_name:
        return get_or_create_source(
            db,
            source_type=source_type,
            name=source_name,
            url=source_homepage_url,
        )
    raise ValueError("source, source_id, or source_type/source_name is required")
