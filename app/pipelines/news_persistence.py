"""Persistence helpers for the news digest pipeline."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from app.curation import item_value, normalize_url, score_item
from app.db.models import DailyDigest
from app.db.repositories import add_digest_item, create_daily_digest, upsert_source_item
from app.db.session import session_scope
from app.schemas import CollectedItem
from app.summarization import DigestSummary
from app.telegram import TelegramDeliveryResult


logger = logging.getLogger(__name__)

DIGEST_TITLE = "Daily AI Technology Digest"


def persist_source_items(
    items: Sequence[CollectedItem],
    *,
    database_url: str,
) -> dict[str, int]:
    """Persist collected source items and return IDs keyed by normalized URL."""

    materialized = list(items)
    persisted: dict[str, int] = {}
    if not materialized:
        return persisted

    logger.info("Persisting %s collected source item(s)", len(materialized))
    with session_scope(database_url) as db:
        for index, item in enumerate(materialized, start=1):
            source_url = _clean_text(item_value(item, "source_url", ""))
            if not source_url:
                continue

            try:
                with db.begin_nested():
                    source_item = upsert_source_item(
                        db,
                        source_type=_clean_text(item_value(item, "source_type", "unknown"))
                        or "unknown",
                        source_name=_clean_text(item_value(item, "source_name", "Unknown"))
                        or "Unknown",
                        external_id=_clean_text(item_value(item, "external_id", "")) or None,
                        title=_title_for_persistence(item),
                        abstract=_clean_text(item_value(item, "abstract", "")) or None,
                        authors=list(item_value(item, "authors", []) or []),
                        published_at=item_value(item, "published_at", None),
                        source_url=source_url,
                        raw_payload=item_value(item, "raw_payload", None),
                    )
                    source_item_id = int(source_item.id)
            except Exception:
                logger.exception("Failed to persist source item: %s", source_url)
                continue

            persisted[normalize_url(source_url)] = source_item_id
            if index % 25 == 0:
                logger.info(
                    "Persisted %s/%s collected source item(s)",
                    index,
                    len(materialized),
                )

    logger.info(
        "Finished source-item persistence with %s unique URL(s)",
        len(persisted),
    )
    return persisted


def persist_digest(
    summaries: Sequence[DigestSummary],
    *,
    selected_items: Sequence[Any],
    persisted_source_items: Mapping[str, int],
    database_url: str,
    digest_date: date,
) -> int | None:
    """Persist the daily digest metadata and publishable digest items."""

    if not summaries:
        with session_scope(database_url) as db:
            digest = create_daily_digest(
                db,
                digest_date=digest_date,
                title=digest_title(digest_date),
                summary="No publishable digest items were prepared.",
                status="empty",
            )
            return int(digest.id)

    selected_by_url = {
        normalize_url(item_value(item, "source_url", "")): item
        for item in selected_items
    }

    with session_scope(database_url) as db:
        digest = create_daily_digest(
            db,
            digest_date=digest_date,
            title=digest_title(digest_date),
            summary=f"Prepared {len(summaries)} digest item(s).",
            status="ready",
        )
        digest_id = int(digest.id)

    for order, summary in enumerate(summaries, start=1):
        source_key = normalize_url(summary.source_url)
        selected_item = selected_by_url.get(source_key)
        source_item_id = persisted_source_items.get(source_key)
        try:
            with session_scope(database_url) as db:
                add_digest_item(
                    db,
                    daily_digest_id=digest_id,
                    source_item_id=source_item_id,
                    title=summary.title,
                    summary=_digest_item_summary(summary),
                    source_url=summary.source_url,
                    item_order=order,
                    importance_score=score_item(selected_item) if selected_item else None,
                )
        except Exception:
            logger.exception("Failed to persist digest item: %s", summary.source_url)

    return digest_id


def update_digest_delivery_status(
    *,
    digest_id: int | None,
    database_url: str,
    sent: bool,
    delivery_results: Sequence[TelegramDeliveryResult],
    has_publishable_items: bool,
) -> None:
    """Update persisted digest status after Telegram delivery."""

    if digest_id is None:
        return

    with session_scope(database_url) as db:
        digest = db.get(DailyDigest, digest_id)
        if digest is None:
            return

        if sent:
            digest.status = "sent"
            digest.sent_at = datetime.now(UTC)
            digest.telegram_message_id = ",".join(
                str(result.telegram_message_id)
                for result in delivery_results
                if result.telegram_message_id is not None
            ) or None
            return

        digest.status = "delivery_failed" if has_publishable_items else "empty"


def digest_title(digest_date: date) -> str:
    """Return the display title for one daily digest."""

    return f"{DIGEST_TITLE} - {digest_date.isoformat()}"


def _digest_item_summary(summary: DigestSummary) -> str:
    return "\n\n".join(
        part
        for part in (
            summary.summary,
            f"Why it matters: {summary.why_it_matters}",
            f"Confidence: {summary.confidence_category}",
        )
        if part
    )


def _title_for_persistence(item: Any) -> str:
    title = _clean_text(item_value(item, "title", ""))
    if title:
        return title

    abstract = _clean_text(item_value(item, "abstract", ""))
    if abstract:
        return abstract[:120]

    return "Untitled source item"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
