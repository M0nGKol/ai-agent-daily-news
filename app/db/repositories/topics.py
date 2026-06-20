"""Repository helpers for topic delivery schedules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TopicDelivery
from app.db.repositories.common import normalize_datetime, require_non_empty


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
            topic_key=require_non_empty("topic_key", str(planned_topic["topic_key"])),
            title=require_non_empty("title", str(planned_topic["title"])),
            category=require_non_empty("category", str(planned_topic["category"])),
            difficulty=require_non_empty("difficulty", str(planned_topic["difficulty"])),
            snippet=require_non_empty("snippet", str(planned_topic["snippet"])),
            why_it_matters=require_non_empty(
                "why_it_matters",
                str(planned_topic["why_it_matters"]),
            ),
            try_this=require_non_empty("try_this", str(planned_topic["try_this"])),
            source_url=require_non_empty("source_url", str(planned_topic["source_url"])),
            scheduled_for=normalize_datetime(planned_topic["scheduled_for"]),
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
        statement = statement.where(TopicDelivery.scheduled_for <= normalize_datetime(now))
        if window_started_at is not None:
            statement = statement.where(
                TopicDelivery.scheduled_for >= normalize_datetime(window_started_at)
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

    delivery.sent_at = normalize_datetime(sent_at)
    delivery.status = "sent"
    message_ids = [str(message_id) for message_id in telegram_message_ids if message_id]
    delivery.telegram_message_id = ",".join(message_ids) or None
    db.flush()
    return delivery
