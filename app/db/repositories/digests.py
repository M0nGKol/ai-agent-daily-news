"""Repository helpers for daily digests and digest items."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import DailyDigest, DigestItem, SourceItem
from app.db.repositories.common import clean_optional_text, require_non_empty


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
    clean_status = require_non_empty("status", status)

    digest = db.scalar(
        select(DailyDigest).where(DailyDigest.digest_date == target_date)
    )
    if digest:
        if title is not None:
            digest.title = clean_optional_text(title)
        if summary is not None:
            digest.summary = summary
        digest.status = clean_status
        db.flush()
        return digest

    digest = DailyDigest(
        digest_date=target_date,
        title=clean_optional_text(title),
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
    clean_title = require_non_empty(
        "title",
        title or (resolved_source_item.title if resolved_source_item else None),
    )
    clean_summary = require_non_empty("summary", summary)
    clean_source_url = require_non_empty(
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


def list_recent_digest_source_urls(
    db: Session,
    *,
    since: date,
    sent_only: bool = True,
) -> set[str]:
    """Return source URLs already included in recent digests."""

    statement = (
        select(DigestItem.source_url)
        .join(DailyDigest)
        .where(DailyDigest.digest_date >= since)
    )
    if sent_only:
        statement = statement.where(DailyDigest.status == "sent")
    return {url for url in db.scalars(statement) if url}


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
