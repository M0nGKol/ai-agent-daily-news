from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.curation.ranking import score_item_breakdown, select_top_items


def test_score_item_breakdown_combines_keyword_recency_and_source_trust(make_item: Any) -> None:
    now = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    item = make_item(
        title="LLM benchmark",
        abstract="LLM benchmark",
        source_name="Trusted Lab",
        published_at=now - timedelta(hours=36),
    )

    score = score_item_breakdown(
        item,
        keyword_weights={"llm": 4.0, "benchmark": 2.0},
        source_trust_map={"Trusted Lab": 9.5},
        now=now,
    )

    assert score.keyword == pytest.approx(15.6)
    assert score.recency == pytest.approx(5.0)
    assert score.source_trust == 9.5
    assert score.total == pytest.approx(30.1)


def test_select_top_items_sorts_filters_and_deduplicates(make_item: Any) -> None:
    now = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    stale = make_item(
        external_id="stale",
        title="Operations note",
        abstract="No notable AI keywords here.",
        source_name="Unknown",
        published_at=now - timedelta(days=30),
        source_url="https://unknown.example/stale",
    )
    duplicate_lower_score = make_item(
        external_id="duplicate",
        title="ai agent benchmark",
        abstract="agent",
        source_name="Unknown",
        published_at=now - timedelta(hours=1),
        source_url="https://mirror.example/duplicate",
    )
    missing_source_url = {
        "external_id": "missing-source",
        "title": "AI agent benchmark",
        "abstract": "agent",
        "source_name": "Trusted",
        "published_at": now.isoformat(),
        "source_url": "",
    }
    second = make_item(
        external_id="second",
        title="AI platform update",
        abstract="",
        source_name="Unknown",
        published_at=now,
        source_url="https://unknown.example/second",
    )
    top = make_item(
        external_id="top",
        title="AI agent benchmark",
        abstract="agent",
        source_name="Trusted",
        published_at=now,
        source_url="https://trusted.example/top",
    )

    selected = select_top_items(
        [stale, duplicate_lower_score, missing_source_url, second, top],
        max_items=2,
        keyword_weights={"ai": 5.0, "agent": 10.0},
        source_trust_map={"Trusted": 10.0, "Unknown": 0.0},
        now=now,
    )

    assert [item.external_id for item in selected] == ["top", "second"]


def test_select_top_items_returns_empty_for_non_positive_limit(make_item: Any) -> None:
    assert select_top_items([make_item()], max_items=0) == []
