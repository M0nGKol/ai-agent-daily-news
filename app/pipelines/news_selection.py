"""Selection and source-registry helpers for the news digest pipeline."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.config import Settings
from app.curation import CurationResult, curate_items, item_value, normalize_url
from app.curation import select_top_items
from app.curation import (
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
from app.summarization import DigestSummary


logger = logging.getLogger(__name__)


def select_digest_items(items: Sequence[Any], *, max_items: int) -> list[Any]:
    """Select a compact daily mix, prioritizing RSS/news while keeping research fallback."""

    if max_items <= 0:
        return []

    news_source_types = {"rss", "news_search"}
    news_items = [
        item
        for item in items
        if _clean_text(item_value(item, "source_type", "")).casefold()
        in news_source_types
    ]
    research_items = [
        item
        for item in items
        if _clean_text(item_value(item, "source_type", "")).casefold()
        not in news_source_types
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


def load_source_registry(settings: Settings) -> SourceRegistry:
    """Load the dynamic source registry and seed it from configured feeds."""

    registry = load_registry(settings.source_state_dir)
    seed_trusted(registry, settings.rss_feed_urls)
    return registry


def curate_digest_selection(
    items: Sequence[Any],
    *,
    settings: Settings,
    registry: SourceRegistry,
    exclude_source_urls: Sequence[str] | set[str] | None = None,
) -> tuple[list[Any], CurationResult]:
    """Classify, drop hype, harvest candidate sources, and select with rotation."""

    excluded_urls = _normalized_url_set(exclude_source_urls or ())
    candidate_items = _exclude_recent_items(items, excluded_urls)
    if excluded_urls:
        logger.info(
            "Filtered %s recently delivered candidate item(s)",
            len(items) - len(candidate_items),
        )

    harvest_candidates(
        registry,
        items,
        high_signal_domains=None,
    )

    curation = curate_items(
        candidate_items,
        max_items=settings.max_digest_items,
        registry=registry,
        max_per_domain=getattr(settings, "max_items_per_source_domain", 1),
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
    fallback = select_digest_items(candidate_items, max_items=settings.max_digest_items)
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


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _exclude_recent_items(items: Sequence[Any], excluded_urls: set[str]) -> list[Any]:
    if not excluded_urls:
        return list(items)
    return [
        item
        for item in items
        if normalize_url(item_value(item, "source_url", "")) not in excluded_urls
    ]


def _normalized_url_set(urls: Sequence[str] | set[str]) -> set[str]:
    return {normalized for url in urls if (normalized := normalize_url(url))}
