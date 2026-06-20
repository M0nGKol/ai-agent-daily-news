from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.items import CollectedItem
from app.curation.curator import curate_items
from app.curation.source_discovery import SourceRegistry, seed_trusted


def _item(title: str, url: str, abstract: str = "") -> CollectedItem:
    return CollectedItem(
        source_type="rss",
        source_name="Example",
        external_id=url,
        title=title,
        abstract=abstract or title,
        authors=[],
        published_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        source_url=url,
    )


def test_curation_drops_hype_and_keeps_engineering() -> None:
    registry = SourceRegistry()
    items = [
        _item("vLLM speeds up inference with paged attention", "https://a.dev/1"),
        _item("Startup raises $50M Series A", "https://b.dev/2"),
        _item("New reranker improves RAG retrieval accuracy", "https://c.dev/3"),
    ]
    result = curate_items(items, max_items=5, registry=registry)
    urls = {i.source_url for i in result.selected}
    assert "https://b.dev/2" not in urls
    assert len(result.selected) == 2
    assert result.dropped_count == 1


def test_curation_respects_max_items() -> None:
    registry = SourceRegistry()
    items = [
        _item(f"LLM fine-tuning recipe number {n}", f"https://a.dev/{n}")
        for n in range(10)
    ]
    result = curate_items(items, max_items=3, registry=registry)
    assert len(result.selected) == 3


def test_bucket_rotation_prefers_variety() -> None:
    registry = SourceRegistry()
    items = [
        _item("LLM inference serving with vLLM throughput", "https://serve.dev/1"),
        _item("LLM inference latency tuning for serving", "https://serve.dev/2"),
        _item("Agent framework adds tool calling and MCP", "https://agent.dev/1"),
    ]
    result = curate_items(items, max_items=2, registry=registry)
    buckets = set(result.bucket_by_url.values())
    # With rotation, two items from different buckets should be chosen.
    assert buckets == {"serving_inference", "agents_orchestration"}


def test_novelty_promotes_fresh_source_over_recent_one() -> None:
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    registry = SourceRegistry(
        trusted={
            "stale.dev": {"trust_score": 8.0},
            "fresh.dev": {"trust_score": 8.0},
        },
        stats={"stale.dev": {"last_posted": "2026-06-14T00:00:00+00:00"}},
    )
    items = [
        _item("LLM fine-tuning with LoRA", "https://stale.dev/1"),
        _item("LLM fine-tuning with LoRA", "https://fresh.dev/1"),
    ]
    result = curate_items(items, max_items=1, registry=registry, now=now)
    # Same content/score base; novelty bonus should favor the fresh source.
    assert result.selected[0].source_url == "https://fresh.dev/1"


def test_empty_input_returns_empty_result() -> None:
    result = curate_items([], max_items=5, registry=SourceRegistry())
    assert result.selected == []


def test_seeded_registry_does_not_break_curation() -> None:
    registry = seed_trusted(SourceRegistry(), ["https://a.dev/feed"])
    items = [_item("RAG retrieval with vector database embeddings", "https://a.dev/1")]
    result = curate_items(items, max_items=5, registry=registry)
    assert len(result.selected) == 1
