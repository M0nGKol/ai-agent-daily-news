"""Daily digest batch job orchestration.

Run with:
    python -m app.jobs.daily_digest
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from app.config import Settings, get_settings
from app.db.models import DailyDigest
from app.db.repositories import (
    add_digest_item,
    create_daily_digest,
    init_db,
    upsert_source_item,
)
from app.db.session import session_scope
from app.schemas import CollectedItem
from app.services.curation import CurationResult, curate_items
from app.services.deduplication import item_value, normalize_url
from app.services.ranking import score_item, select_top_items
from app.services.source_discovery import (
    SourceRegistry,
    demote_stale_sources,
    domain_of,
    harvest_candidates,
    load_registry,
    promote_candidates,
    record_dropped,
    record_posted,
    save_registry,
    seed_trusted,
)
from app.services.summarization import DigestSummary, create_summarizer
from app.services.telegram import (
    TelegramConfigurationError,
    TelegramDeliveryResult,
    send_digest_to_telegram,
)
from app.utils.logging import configure_logging


logger = logging.getLogger(__name__)

DIGEST_TITLE = "Daily AI Technology Digest"
DEFAULT_SQLITE_DATABASE_URL = "sqlite:///./daily_digest.db"


@dataclass(frozen=True)
class CollectorOutcome:
    """Result of one collector execution."""

    name: str
    item_count: int
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the collector completed without an unhandled exception."""

        return self.error is None


@dataclass(frozen=True)
class DailyDigestRunResult:
    """Structured result for the daily digest job."""

    collected_count: int
    selected_count: int
    summarized_count: int
    persisted_source_count: int
    digest_id: int | None
    delivery_attempted: bool
    delivery_succeeded: bool
    collector_outcomes: tuple[CollectorOutcome, ...]
    errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Return whether the job produced and delivered a digest."""

        return self.summarized_count > 0 and self.delivery_succeeded and not self.errors


def main() -> int:
    """Run the daily digest job and return a process exit code."""

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
        result = run_daily_digest(settings)
    except Exception:
        logger.exception("Daily digest job failed unexpectedly")
        return 1

    _log_run_result(result)
    return 0 if result.succeeded else 1


def run_daily_digest(settings: Settings | None = None) -> DailyDigestRunResult:
    """Collect, rank, summarize, persist, and deliver the daily digest."""

    resolved_settings = settings or get_settings()
    database_url = resolved_settings.database_url or DEFAULT_SQLITE_DATABASE_URL
    digest_date = datetime.now(UTC).date()

    init_db(database_url)
    logger.info("Initialized digest database")

    collected_items, collector_outcomes = collect_daily_items(resolved_settings)
    logger.info("Collected %s candidate item(s)", len(collected_items))

    persisted_source_items = persist_source_items(
        collected_items,
        database_url=database_url,
    )

    registry = _load_source_registry(resolved_settings)
    selected_items, curation = curate_digest_selection(
        collected_items,
        settings=resolved_settings,
        registry=registry,
    )
    logger.info(
        "Curated %s item(s); dropped %s as off-scope/hype",
        len(selected_items),
        curation.dropped_count,
    )

    summaries = summarize_selected_items(selected_items, resolved_settings)
    logger.info("Prepared %s publishable summary item(s)", len(summaries))

    digest_id = persist_digest(
        summaries,
        selected_items=selected_items,
        persisted_source_items=persisted_source_items,
        database_url=database_url,
        digest_date=digest_date,
    )

    errors: list[str] = []
    delivery_results: list[TelegramDeliveryResult] = []
    delivery_attempted = bool(summaries)
    if summaries:
        try:
            delivery_results = send_digest_to_telegram(
                _telegram_items_for_summaries(summaries, selected_items),
                title=_digest_title(digest_date),
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


def collect_daily_items(
    settings: Settings,
) -> tuple[list[CollectedItem], list[CollectorOutcome]]:
    """Run all configured collectors and keep successful partial results."""

    # Fetch a wider pool than we publish: classification drops off-scope/hype
    # items and bucket rotation needs candidates across buckets to choose from.
    max_results = max(settings.max_digest_items * 3, settings.max_digest_items)
    collectors: tuple[tuple[str, Callable[[], list[CollectedItem]]], ...] = (
        (
            "RSS",
            lambda: _collect_rss_items(
                settings.rss_feed_urls,
                limit_per_feed=max(1, max_results),
            ),
        ),
        (
            "arXiv",
            lambda: _collect_arxiv_papers(
                max_results=max(2, max_results),
                timeout=settings.http_timeout_seconds,
            ),
        ),
        (
            "Semantic Scholar",
            lambda: _collect_semantic_scholar_papers(
                limit=max(2, max_results),
                api_key=settings.semantic_scholar_api_key,
                timeout=settings.http_timeout_seconds,
            ),
        ),
    )

    collected_items: list[CollectedItem] = []
    outcomes: list[CollectorOutcome] = []
    for name, collect in collectors:
        items, outcome = _run_collector(name, collect)
        collected_items.extend(items)
        outcomes.append(outcome)

    return collected_items, outcomes


def select_digest_items(items: Sequence[Any], *, max_items: int) -> list[Any]:
    """Select a compact daily mix, prioritizing RSS/news while keeping research fallback."""
    if max_items <= 0:
        return []

    news_items = [
        item
        for item in items
        if _clean_text(item_value(item, "source_type", "")).casefold() == "rss"
    ]
    research_items = [
        item
        for item in items
        if _clean_text(item_value(item, "source_type", "")).casefold() != "rss"
    ]
    target_news_count = max_items if news_items else 0

    selected_news = select_top_items(
        news_items,
        max_items=target_news_count,
        deduplicate=True,
        require_source_url=True,
    )
    selected_research = select_top_items(
        research_items,
        max_items=max_items - len(selected_news),
        deduplicate=True,
        require_source_url=True,
    )
    selected = selected_news + selected_research

    if len(selected) < max_items:
        seen_urls = {normalize_url(item_value(item, "source_url", "")) for item in selected}
        filler_items = [
            item
            for item in select_top_items(
                items,
                max_items=max_items,
                deduplicate=True,
                require_source_url=True,
            )
            if normalize_url(item_value(item, "source_url", "")) not in seen_urls
        ]
        selected = (selected + filler_items)[:max_items]

    if not selected:
        selected = select_top_items(
            items,
            max_items=max_items,
            deduplicate=True,
            require_source_url=True,
        )

    return selected[:max_items]


def _load_source_registry(settings: Settings) -> SourceRegistry:
    """Load the dynamic source registry and seed it from configured feeds."""

    registry = load_registry(settings.source_state_dir)
    seed_trusted(registry, settings.rss_feed_urls)
    return registry


def curate_digest_selection(
    items: Sequence[Any],
    *,
    settings: Settings,
    registry: SourceRegistry,
) -> tuple[list[Any], CurationResult]:
    """Classify, drop hype, harvest candidate sources, and select with rotation.

    Falls back to the legacy ranking selection only if curation keeps nothing, so
    a quiet news day still yields a digest instead of an empty channel.
    """

    harvest_candidates(
        registry,
        items,
        high_signal_domains=None,
    )

    curation = curate_items(
        items,
        max_items=settings.max_digest_items,
        registry=registry,
    )

    # Refresh high-signal flags for domains that survived classification.
    harvest_candidates(
        registry,
        [],
        high_signal_domains=curation.kept_domains,
    )

    if curation.selected:
        return curation.selected, curation

    logger.warning("Curation kept no items; falling back to legacy ranking selection")
    fallback = select_digest_items(items, max_items=settings.max_digest_items)
    return fallback, curation


def finalize_source_registry(
    registry: SourceRegistry,
    *,
    settings: Settings,
    curation: CurationResult,
    delivered: bool,
    delivered_summaries: Sequence[DigestSummary],
) -> None:
    """Record posted/dropped stats, promote/demote sources, and persist state."""

    try:
        if delivered:
            posted_domains = [
                domain_of(summary.source_url) for summary in delivered_summaries
            ]
            record_posted(registry, [d for d in posted_domains if d])

        posted_set = {
            domain_of(summary.source_url) for summary in delivered_summaries
        } if delivered else set()
        dropped_domains = [
            domain for domain in curation.kept_domains if domain not in posted_set
        ]
        record_dropped(registry, dropped_domains)

        promoted = promote_candidates(registry)
        demoted = demote_stale_sources(registry)
        if promoted:
            logger.info("Promoted source(s) to trusted: %s", ", ".join(promoted))
        if demoted:
            logger.info("Demoted stale source(s): %s", ", ".join(demoted))

        save_registry(registry, settings.source_state_dir)
    except Exception:
        logger.exception("Failed to update source discovery registry")


def _collect_arxiv_papers(*, max_results: int, timeout: float) -> list[CollectedItem]:
    from app.collectors.arxiv import collect_arxiv_papers

    return collect_arxiv_papers(max_results=max_results, timeout=timeout)


def _collect_semantic_scholar_papers(
    *,
    limit: int,
    api_key: str | None,
    timeout: float,
) -> list[CollectedItem]:
    from app.collectors.semantic_scholar import collect_semantic_scholar_papers

    return collect_semantic_scholar_papers(
        limit=limit,
        api_key=api_key,
        timeout=timeout,
    )


def _collect_rss_items(
    feed_urls: Sequence[str],
    *,
    limit_per_feed: int,
) -> list[CollectedItem]:
    from app.collectors.rss import collect_rss_items

    return collect_rss_items(feed_urls, limit_per_feed=limit_per_feed)


def persist_source_items(
    items: Sequence[CollectedItem],
    *,
    database_url: str,
) -> dict[str, int]:
    """Persist collected source items and return IDs keyed by normalized URL."""

    persisted: dict[str, int] = {}
    for item in items:
        source_url = _clean_text(item_value(item, "source_url", ""))
        if not source_url:
            continue

        try:
            with session_scope(database_url) as db:
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

    return persisted


def summarize_selected_items(
    items: Sequence[Any],
    settings: Settings,
) -> list[DigestSummary]:
    """Create publishable summaries for selected items."""

    summarizer = create_summarizer(config=_summarizer_config(settings))
    summaries: list[DigestSummary] = []

    for item in items:
        source_url = _clean_text(item_value(item, "source_url", ""))
        if not source_url:
            continue
        try:
            summaries.append(summarizer.summarize(item))
        except ValueError as exc:
            logger.warning("Skipping item that failed summary validation: %s", exc)
        except Exception:
            logger.exception("Skipping item after summarization failure: %s", source_url)

    return summaries


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
                title=_digest_title(digest_date),
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
            title=_digest_title(digest_date),
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


def _run_collector(
    name: str,
    collect: Callable[[], list[CollectedItem]],
) -> tuple[list[CollectedItem], CollectorOutcome]:
    try:
        items = collect()
    except Exception as exc:
        logger.exception("%s collector failed", name)
        return [], CollectorOutcome(name=name, item_count=0, error=str(exc))

    logger.info("%s collector returned %s item(s)", name, len(items))
    return items, CollectorOutcome(name=name, item_count=len(items))


def _summarizer_config(settings: Settings) -> dict[str, Any]:
    return {
        "LLM_PROVIDER": settings.llm_provider,
        "LLM_API_KEY": settings.llm_api_key,
        "LLM_MODEL": settings.llm_model,
        "LLM_BASE_URL": settings.llm_base_url,
    }


def _summary_to_telegram_item(summary: DigestSummary) -> dict[str, Any]:
    return {
        "title": summary.title,
        "summary": summary.summary,
        "why_it_matters": summary.why_it_matters,
        "source_url": summary.source_url,
        "category": summary.source_name or summary.source_type or "",
    }


def _telegram_items_for_summaries(
    summaries: Sequence[DigestSummary],
    selected_items: Sequence[Any],
) -> list[dict[str, Any]]:
    selected_by_url = {
        normalize_url(item_value(item, "source_url", "")): item for item in selected_items
    }
    telegram_items: list[dict[str, Any]] = []
    for summary in summaries:
        item = _summary_to_telegram_item(summary)
        selected_item = selected_by_url.get(normalize_url(summary.source_url))
        image_url = _clean_text(item_value(selected_item, "image_url", ""))
        if image_url:
            item["image_url"] = image_url
        telegram_items.append(item)
    return telegram_items


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


def _digest_title(digest_date: date) -> str:
    return f"{DIGEST_TITLE} - {digest_date.isoformat()}"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _log_run_result(result: DailyDigestRunResult) -> None:
    logger.info("Daily digest result: %s", asdict(result))

    for error in result.errors:
        logger.error("Daily digest error: %s", error)

    failed_collectors = [
        outcome.name for outcome in result.collector_outcomes if not outcome.succeeded
    ]
    if failed_collectors:
        logger.warning("Collectors failed: %s", ", ".join(failed_collectors))


if __name__ == "__main__":
    sys.exit(main())
