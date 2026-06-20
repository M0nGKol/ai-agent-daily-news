"""Collection helpers for the news digest pipeline."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from app.config import Settings
from app.pipelines.news_models import CollectorOutcome
from app.schemas import CollectedItem


logger = logging.getLogger(__name__)


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
        *(
            (
                (
                    "GDELT",
                    lambda: _collect_gdelt_articles(
                        query=settings.gdelt_query,
                        timespan=settings.gdelt_timespan,
                        max_records=settings.gdelt_max_records,
                        timeout=settings.http_timeout_seconds,
                    ),
                ),
            )
            if settings.gdelt_enabled
            else ()
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


def _collect_gdelt_articles(
    *,
    query: str,
    timespan: str,
    max_records: int,
    timeout: float,
) -> list[CollectedItem]:
    from app.collectors.gdelt import collect_gdelt_articles

    return collect_gdelt_articles(
        query=query,
        timespan=timespan,
        max_records=max_records,
        timeout=timeout,
    )


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
