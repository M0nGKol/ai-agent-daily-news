from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.jobs.daily_digest import (
    curate_digest_selection,
    finalize_source_registry,
    select_digest_items,
)
from app.schemas.items import CollectedItem
from app.services.curation import CurationResult
from app.services.source_discovery import SourceRegistry, load_registry


def test_select_digest_items_limits_to_five_and_prefers_news() -> None:
    now = datetime.now(timezone.utc)
    items = [
        CollectedItem(
            source_type="rss",
            source_name=f"News Source {index}",
            external_id=f"news-{index}",
            title=f"AI news update {index}",
            abstract="A news story about AI product launches and engineering updates.",
            authors=[],
            published_at=now - timedelta(hours=index),
            source_url=f"https://news.example.com/{index}",
            image_url=f"https://news.example.com/{index}.jpg",
        )
        for index in range(6)
    ] + [
        CollectedItem(
            source_type="paper",
            source_name="arXiv",
            external_id=f"paper-{index}",
            title=f"LLM benchmark paper {index}",
            abstract="A paper about LLM benchmark evaluation and reasoning.",
            authors=[],
            published_at=now,
            source_url=f"https://arxiv.org/abs/2601.0000{index}",
        )
        for index in range(6)
    ]

    selected = select_digest_items(items, max_items=5)

    assert len(selected) == 5
    assert all(item.source_type == "rss" for item in selected)


def _news(title: str, url: str) -> CollectedItem:
    return CollectedItem(
        source_type="rss",
        source_name="Example",
        external_id=url,
        title=title,
        abstract=title,
        authors=[],
        published_at=datetime.now(timezone.utc),
        source_url=url,
    )


def test_curate_digest_selection_drops_hype_and_harvests_sources() -> None:
    settings = SimpleNamespace(max_digest_items=5)
    registry = SourceRegistry()
    items = [
        _news("vLLM improves inference throughput with paged attention", "https://a.dev/1"),
        _news("Startup raises $100M Series B at huge valuation", "https://b.dev/2"),
        _news("New reranker boosts RAG retrieval quality", "https://c.dev/3"),
    ]

    selected, curation = curate_digest_selection(
        items, settings=settings, registry=registry
    )

    selected_urls = {item.source_url for item in selected}
    assert "https://b.dev/2" not in selected_urls
    assert len(selected) == 2
    assert isinstance(curation, CurationResult)
    # Non-trusted domains seen this run should be pooled as candidates.
    assert "a.dev" in registry.candidates


def test_finalize_source_registry_records_stats_and_persists(tmp_path) -> None:
    settings = SimpleNamespace(source_state_dir=str(tmp_path))
    registry = SourceRegistry()
    curation = CurationResult(kept_domains=["a.dev", "c.dev"])
    delivered_summary = SimpleNamespace(source_url="https://a.dev/1")

    finalize_source_registry(
        registry,
        settings=settings,
        curation=curation,
        delivered=True,
        delivered_summaries=[delivered_summary],
    )

    reloaded = load_registry(tmp_path)
    assert reloaded.stats["a.dev"]["posted"] == 1
    # Kept-but-not-posted domains are recorded as dropped.
    assert reloaded.stats["c.dev"]["dropped"] == 1
