"""News digest pipeline orchestration."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from app.config import DEFAULT_SQLITE_DATABASE_URL, Settings, get_settings
from app.db.repositories import init_db, list_recent_digest_source_urls
from app.db.session import session_scope
from app.pipelines.news_collection import collect_daily_items
from app.pipelines.news_delivery import telegram_items_for_summaries
from app.pipelines.news_models import CollectorOutcome, DailyDigestRunResult
from app.pipelines.news_persistence import (
    digest_title,
    persist_digest,
    persist_source_items,
    update_digest_delivery_status,
)
from app.pipelines.news_selection import (
    curate_digest_selection,
    finalize_source_registry,
    load_source_registry,
)
from app.pipelines.news_summaries import summarize_selected_items
from app.telegram import (
    TelegramConfigurationError,
    TelegramDeliveryResult,
    send_digest_to_telegram,
)


logger = logging.getLogger(__name__)

__all__ = [
    "CollectorOutcome",
    "DailyDigestRunResult",
    "collect_daily_items",
    "curate_digest_selection",
    "finalize_source_registry",
    "persist_digest",
    "persist_source_items",
    "run_daily_digest",
    "summarize_selected_items",
    "update_digest_delivery_status",
]


def run_daily_digest(settings: Settings | None = None) -> DailyDigestRunResult:
    """Collect, rank, summarize, persist, and deliver the daily digest."""

    resolved_settings = settings or get_settings()
    database_url = resolved_settings.database_url or DEFAULT_SQLITE_DATABASE_URL
    run_date = datetime.now(UTC).date()

    init_db(database_url)
    logger.info("Initialized digest database")

    collected_items, collector_outcomes = collect_daily_items(resolved_settings)
    logger.info("Collected %s candidate item(s)", len(collected_items))

    logger.info("Persisting collected source items")
    persisted_source_items = persist_source_items(
        collected_items,
        database_url=database_url,
    )
    logger.info("Persisted %s unique source item URL(s)", len(persisted_source_items))

    logger.info("Loading source registry and curating candidates")
    registry = load_source_registry(resolved_settings)
    recent_source_urls = _recent_digest_source_urls(
        database_url=database_url,
        run_date=run_date,
        lookback_days=resolved_settings.digest_repeat_lookback_days,
    )
    if recent_source_urls:
        logger.info(
            "Loaded %s recently delivered source URL(s) for repeat filtering",
            len(recent_source_urls),
        )
    selected_items, curation = curate_digest_selection(
        collected_items,
        settings=resolved_settings,
        registry=registry,
        exclude_source_urls=recent_source_urls,
    )
    logger.info(
        "Curated %s item(s); dropped %s as off-scope/hype",
        len(selected_items),
        curation.dropped_count,
    )

    logger.info("Summarizing %s selected item(s)", len(selected_items))
    summaries = summarize_selected_items(selected_items, resolved_settings)
    logger.info("Prepared %s publishable summary item(s)", len(summaries))

    logger.info("Persisting digest record")
    digest_id = persist_digest(
        summaries,
        selected_items=selected_items,
        persisted_source_items=persisted_source_items,
        database_url=database_url,
        digest_date=run_date,
    )

    errors: list[str] = []
    delivery_results: list[TelegramDeliveryResult] = []
    delivery_attempted = bool(summaries)
    if summaries:
        try:
            logger.info("Delivering digest to Telegram")
            delivery_results = send_digest_to_telegram(
                telegram_items_for_summaries(summaries, selected_items),
                title=digest_title(run_date),
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

    update_digest_delivery_status(
        digest_id=digest_id,
        database_url=database_url,
        sent=delivery_succeeded,
        delivery_results=delivery_results,
        has_publishable_items=bool(summaries),
    )

    finalize_source_registry(
        registry,
        settings=resolved_settings,
        curation=curation,
        delivered=delivery_succeeded,
        delivered_summaries=summaries,
    )

    return DailyDigestRunResult(
        collected_count=len(collected_items),
        selected_count=len(selected_items),
        summarized_count=len(summaries),
        persisted_source_count=len(persisted_source_items),
        digest_id=digest_id,
        delivery_attempted=delivery_attempted,
        delivery_succeeded=delivery_succeeded,
        collector_outcomes=tuple(collector_outcomes),
        errors=tuple(errors),
    )


def _log_run_result(result: DailyDigestRunResult) -> None:
    logger.info("Daily digest result: %s", asdict(result))

    for error in result.errors:
        logger.error("Daily digest error: %s", error)

    failed_collectors = [
        outcome.name for outcome in result.collector_outcomes if not outcome.succeeded
    ]
    if failed_collectors:
        logger.warning("Collectors failed: %s", ", ".join(failed_collectors))


def _recent_digest_source_urls(
    *,
    database_url: str,
    run_date,
    lookback_days: int,
) -> set[str]:
    since = run_date - timedelta(days=max(lookback_days - 1, 0))
    with session_scope(database_url) as db:
        return list_recent_digest_source_urls(db, since=since, sent_only=True)
