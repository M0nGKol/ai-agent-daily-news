"""Randomized daily AI learning topic delivery.

Run once an hour with:
    python -m app.jobs.daily_topics

Force the next unsent topic for local testing with:
    python -m app.jobs.daily_topics --send-now
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from app.config import DEFAULT_SQLITE_DATABASE_URL, Settings, get_settings
from app.db.models import TopicDelivery
from app.db.repositories import (
    create_topic_delivery_plan,
    get_due_topic_delivery,
    init_db,
    mark_topic_delivery_sent,
)
from app.db.session import session_scope
from app.telegram import (
    TelegramConfigurationError,
    TelegramDeliveryResult,
    send_telegram_messages,
)
from app.services.topic_briefing import (
    build_daily_topic_plan,
    format_topic_card_message,
)
from app.utils.logging import configure_logging


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyTopicRunResult:
    """Structured result for one hourly topic delivery attempt."""

    delivery_date: date
    planned_count: int
    sent_count: int
    due_topic_id: int | None
    delivery_attempted: bool
    delivery_succeeded: bool
    reason: str
    errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Return whether the run should exit successfully."""
        return not self.errors and (not self.delivery_attempted or self.delivery_succeeded)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the topic delivery job and return a process exit code."""
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(
        extra_secret_values=(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            settings.llm_api_key,
            settings.semantic_scholar_api_key,
        )
    )

    try:
        result = run_daily_topics(settings=settings, force=args.send_now)
    except Exception:
        logger.exception("Daily topic job failed unexpectedly")
        return 1

    logger.info("Daily topic result: %s", asdict(result))
    for error in result.errors:
        logger.error("Daily topic error: %s", error)
    return 0 if result.succeeded else 1


def run_daily_topics(
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> DailyTopicRunResult:
    """Plan today's five topics and send at most one due topic card."""
    resolved_settings = settings or get_settings()
    current_time = _aware_utc(now or datetime.now(UTC))
    local_date = current_time.astimezone(ZoneInfo(resolved_settings.topic_timezone)).date()
    database_url = resolved_settings.database_url or DEFAULT_SQLITE_DATABASE_URL

    init_db(database_url)
    planned_topics = [
        planned_topic.to_repository_dict()
        for planned_topic in build_daily_topic_plan(
            local_date,
            count=resolved_settings.max_digest_items,
            timezone_name=resolved_settings.topic_timezone,
            start_hour=resolved_settings.topic_send_start_hour,
            end_hour=resolved_settings.topic_send_end_hour,
        )
    ]

    with session_scope(database_url) as db:
        plan = create_topic_delivery_plan(
            db,
            delivery_date=local_date,
            planned_topics=planned_topics,
        )
        due_topic = get_due_topic_delivery(
            db,
            delivery_date=local_date,
            now=current_time,
            force=force,
            window_started_at=(
                None
                if force
                else current_time - timedelta(minutes=resolved_settings.topic_due_window_minutes)
            ),
        )
        due_topic_id = int(due_topic.id) if due_topic is not None else None
        if due_topic is None:
            return DailyTopicRunResult(
                delivery_date=local_date,
                planned_count=len(plan),
                sent_count=0,
                due_topic_id=None,
                delivery_attempted=False,
                delivery_succeeded=False,
                reason="No unsent topic is due yet.",
            )
        topic_payload = _topic_payload(due_topic)

    errors: list[str] = []
    delivery_results: list[TelegramDeliveryResult] = []
    try:
        delivery_results = send_telegram_messages(
            [
                format_topic_card_message(
                    topic_payload,
                    total=resolved_settings.max_digest_items,
                )
            ],
            bot_token=resolved_settings.telegram_bot_token,
            chat_id=resolved_settings.telegram_chat_id,
            timeout_seconds=resolved_settings.http_timeout_seconds,
        )
    except TelegramConfigurationError as exc:
        errors.append(str(exc))
        logger.error("Telegram delivery is not configured: %s", exc)
    except Exception as exc:
        errors.append(f"Telegram delivery failed: {exc.__class__.__name__}")
        logger.exception("Telegram delivery failed")

    delivery_succeeded = bool(delivery_results) and all(
        result.ok for result in delivery_results
    )
    errors.extend(
        result.error
        for result in delivery_results
        if not result.ok and result.error is not None
    )

    if delivery_succeeded and due_topic_id is not None:
        with session_scope(database_url) as db:
            delivery = db.get(TopicDelivery, due_topic_id)
            if delivery is not None:
                mark_topic_delivery_sent(
                    db,
                    delivery=delivery,
                    sent_at=current_time,
                    telegram_message_ids=[
                        result.telegram_message_id for result in delivery_results
                    ],
                )

    return DailyTopicRunResult(
        delivery_date=local_date,
        planned_count=len(planned_topics),
        sent_count=1 if delivery_succeeded else 0,
        due_topic_id=due_topic_id,
        delivery_attempted=True,
        delivery_succeeded=delivery_succeeded,
        reason="Sent one due topic." if delivery_succeeded else "Failed to send due topic.",
        errors=tuple(errors),
    )


def _topic_payload(delivery: TopicDelivery) -> dict[str, object]:
    return {
        "item_order": delivery.item_order,
        "title": delivery.title,
        "category": delivery.category,
        "difficulty": delivery.difficulty,
        "snippet": delivery.snippet,
        "why_it_matters": delivery.why_it_matters,
        "try_this": delivery.try_this,
        "source_url": delivery.source_url,
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one due daily AI topic card.")
    parser.add_argument(
        "--send-now",
        action="store_true",
        help="send the next unsent topic immediately, ignoring its scheduled time",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
