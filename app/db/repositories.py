"""Repository helpers for sources, collected items, and daily digests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import DailyDigest, DigestItem, Source, SourceItem, TopicDelivery
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


def get_or_create_source(
    db: Session,
    *,
    source_type: str,
    name: str,
    url: str | None = None,
    is_active: bool = True,
) -> Source:
    """Return an existing source by type/name, or create it."""
    clean_source_type = _require_non_empty("source_type", source_type)
    clean_name = _require_non_empty("name", name)
    clean_url = _clean_optional_text(url)

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
    clean_title = _require_non_empty("title", title)
    clean_source_url = _require_non_empty("source_url", source_url)
    clean_external_id = _clean_optional_text(external_id)
    owner = _resolve_source(
        db,
        source=source,
        source_id=source_id,
        source_type=source_type,
        source_name=source_name,
        source_homepage_url=source_homepage_url,
    )
    clean_hash = _clean_optional_text(content_hash) or _content_hash(
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
            published_at=_normalize_datetime(published_at),
            source_url=clean_source_url,
            content_hash=clean_hash,
            raw_payload=_normalize_json_payload(raw_payload),
        )
        db.add(item)
    else:
        item.source_id = owner.id
        item.external_id = clean_external_id or item.external_id
        item.title = clean_title
        item.abstract = abstract
        item.authors = list(authors or [])
        item.published_at = _normalize_datetime(published_at)
        item.source_url = clean_source_url
        item.content_hash = clean_hash
        item.raw_payload = _normalize_json_payload(raw_payload)

    db.flush()
    return item


def create_daily_digest(
    db: Session,
    *,
    digest_date: date | None = None,
    title: str | None = None,
    summary: str | None = None,
    status: str = "draft",
) -> DailyDigest:
    """Create or return the digest for a date, updating supplied metadata."""
    target_date = digest_date or datetime.now(UTC).date()
    clean_status = _require_non_empty("status", status)

    digest = db.scalar(
        select(DailyDigest).where(DailyDigest.digest_date == target_date)
    )
    if digest:
        if title is not None:
            digest.title = _clean_optional_text(title)
        if summary is not None:
            digest.summary = summary
        digest.status = clean_status
        db.flush()
        return digest

    digest = DailyDigest(
        digest_date=target_date,
        title=_clean_optional_text(title),
        summary=summary,
        status=clean_status,
    )
    db.add(digest)
    db.flush()
    return digest


def add_digest_item(
    db: Session,
    *,
    daily_digest: DailyDigest | None = None,
    daily_digest_id: int | None = None,
    source_item: SourceItem | None = None,
    source_item_id: int | None = None,
    title: str | None = None,
    summary: str,
    source_url: str | None = None,
    item_order: int = 0,
    importance_score: float | None = None,
) -> DigestItem:
    """Add or update an item in a digest while requiring a source URL."""
    digest = _resolve_digest(db, daily_digest=daily_digest, daily_digest_id=daily_digest_id)
    resolved_source_item = _resolve_source_item(
        db,
        source_item=source_item,
        source_item_id=source_item_id,
    )
    clean_title = _require_non_empty(
        "title",
        title or (resolved_source_item.title if resolved_source_item else None),
    )
    clean_summary = _require_non_empty("summary", summary)
    clean_source_url = _require_non_empty(
        "source_url",
        source_url or (resolved_source_item.source_url if resolved_source_item else None),
    )

    digest_item = _find_existing_digest_item(
        db,
        daily_digest_id=digest.id,
        source_item_id=resolved_source_item.id if resolved_source_item else None,
        source_url=clean_source_url,
    )

    if digest_item is None:
        digest_item = DigestItem(
            daily_digest_id=digest.id,
            source_item_id=resolved_source_item.id if resolved_source_item else None,
            title=clean_title,
            summary=clean_summary,
            source_url=clean_source_url,
            item_order=item_order,
            importance_score=importance_score,
        )
        db.add(digest_item)
    else:
        digest_item.source_item_id = (
            resolved_source_item.id if resolved_source_item else digest_item.source_item_id
        )
        digest_item.title = clean_title
        digest_item.summary = clean_summary
        digest_item.source_url = clean_source_url
        digest_item.item_order = item_order
        digest_item.importance_score = importance_score

    db.flush()
    return digest_item


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
        normalized_since = _normalize_datetime(since)
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


def create_topic_delivery_plan(
    db: Session,
    *,
    delivery_date: date,
    planned_topics: Sequence[Mapping[str, Any]],
) -> list[TopicDelivery]:
    """Create or return the scheduled topic cards for a delivery date."""
    existing = list(
        db.scalars(
            select(TopicDelivery)
            .where(TopicDelivery.delivery_date == delivery_date)
            .order_by(TopicDelivery.item_order)
        )
    )
    if existing:
        return existing

    deliveries: list[TopicDelivery] = []
    for planned_topic in planned_topics:
        delivery = TopicDelivery(
            delivery_date=delivery_date,
            item_order=int(planned_topic["item_order"]),
            topic_key=_require_non_empty("topic_key", str(planned_topic["topic_key"])),
            title=_require_non_empty("title", str(planned_topic["title"])),
            category=_require_non_empty("category", str(planned_topic["category"])),
            difficulty=_require_non_empty("difficulty", str(planned_topic["difficulty"])),
            snippet=_require_non_empty("snippet", str(planned_topic["snippet"])),
            why_it_matters=_require_non_empty(
                "why_it_matters",
                str(planned_topic["why_it_matters"]),
            ),
            try_this=_require_non_empty("try_this", str(planned_topic["try_this"])),
            source_url=_require_non_empty("source_url", str(planned_topic["source_url"])),
            scheduled_for=_normalize_datetime(planned_topic["scheduled_for"]),
            status="scheduled",
        )
        db.add(delivery)
        deliveries.append(delivery)

    db.flush()
    return deliveries


def get_due_topic_delivery(
    db: Session,
    *,
    delivery_date: date,
    now: datetime,
    force: bool = False,
    window_started_at: datetime | None = None,
) -> TopicDelivery | None:
    """Return the next unsent topic that is due for the local delivery date."""
    statement = (
        select(TopicDelivery)
        .where(
            TopicDelivery.delivery_date == delivery_date,
            TopicDelivery.sent_at.is_(None),
            TopicDelivery.status == "scheduled",
        )
    )
    if not force:
        statement = statement.where(TopicDelivery.scheduled_for <= _normalize_datetime(now))
        if window_started_at is not None:
            statement = statement.where(
                TopicDelivery.scheduled_for >= _normalize_datetime(window_started_at)
            )
        statement = statement.order_by(TopicDelivery.scheduled_for.desc())
    else:
        statement = statement.order_by(TopicDelivery.item_order)

    return db.scalar(statement.limit(1))


def mark_topic_delivery_sent(
    db: Session,
    *,
    delivery: TopicDelivery,
    sent_at: datetime,
    telegram_message_ids: Sequence[int | str | None],
) -> TopicDelivery:
    """Mark one topic card as sent."""
    delivery.sent_at = _normalize_datetime(sent_at)
    delivery.status = "sent"
    message_ids = [str(message_id) for message_id in telegram_message_ids if message_id]
    delivery.telegram_message_id = ",".join(message_ids) or None
    db.flush()
    return delivery


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


def _find_existing_digest_item(
    db: Session,
    *,
    daily_digest_id: int,
    source_item_id: int | None,
    source_url: str,
) -> DigestItem | None:
    conditions = [DigestItem.source_url == source_url]
    if source_item_id is not None:
        conditions.append(DigestItem.source_item_id == source_item_id)

    return db.scalar(
        select(DigestItem)
        .where(
            DigestItem.daily_digest_id == daily_digest_id,
            or_(*conditions),
        )
        .order_by(DigestItem.id)
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


def _resolve_digest(
    db: Session,
    *,
    daily_digest: DailyDigest | None,
    daily_digest_id: int | None,
) -> DailyDigest:
    if daily_digest is not None:
        return daily_digest
    if daily_digest_id is None:
        raise ValueError("daily_digest or daily_digest_id is required")
    digest = db.get(DailyDigest, daily_digest_id)
    if digest is None:
        raise ValueError(f"daily_digest_id {daily_digest_id} does not exist")
    return digest


def _resolve_source_item(
    db: Session,
    *,
    source_item: SourceItem | None,
    source_item_id: int | None,
) -> SourceItem | None:
    if source_item is not None:
        return source_item
    if source_item_id is None:
        return None
    item = db.get(SourceItem, source_item_id)
    if item is None:
        raise ValueError(f"source_item_id {source_item_id} does not exist")
    return item


def _content_hash(*, title: str, abstract: str | None, source_url: str) -> str:
    normalized = "\n".join(
        [
            title.strip().casefold(),
            (abstract or "").strip().casefold(),
            source_url.strip(),
        ]
    )
    return sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_json_payload(payload: JsonPayload | None) -> dict[str, Any] | list[Any] | None:
    if payload is None:
        return None
    if isinstance(payload, Mapping):
        return dict(payload)
    return list(payload)


def _require_non_empty(field_name: str, value: str | None) -> str:
    cleaned = _clean_optional_text(value)
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
