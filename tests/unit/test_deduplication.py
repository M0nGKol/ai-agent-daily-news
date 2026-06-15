from __future__ import annotations

from typing import Any

from app.services.deduplication import deduplicate_items, normalize_url


def test_normalize_url_removes_tracking_and_preserves_meaningful_query() -> None:
    normalized = normalize_url(
        "HTTPS://www.Example.com//Path//Item/?utm_source=newsletter&b=2&a=1#section"
    )

    assert normalized == "https://example.com/Path/Item?a=1&b=2"


def test_deduplicate_items_keeps_first_duplicate_by_url_or_title(make_item: Any) -> None:
    first = make_item(
        external_id="first",
        source_url="https://example.com/articles/ai?id=1&utm_campaign=digest#top",
        title="AI Agent Benchmark Released",
        abstract="A detailed source about AI agent benchmark design and evaluation.",
    )
    duplicate_url = make_item(
        external_id="duplicate-url",
        source_url="https://www.example.com//articles/ai?id=1",
        title="Different headline",
        abstract="Another source with enough content to produce a content hash.",
    )
    duplicate_title = make_item(
        external_id="duplicate-title",
        source_url="https://other.example/articles/ai",
        title="  ai agent benchmark released  ",
        abstract="Different abstract, but same normalized title.",
    )
    unique = make_item(
        external_id="unique",
        source_url="https://example.com/articles/unique",
        title="New multimodal model released",
        abstract="A distinct source about multimodal model release details.",
    )

    deduped = deduplicate_items([first, duplicate_url, duplicate_title, unique])

    assert [item.external_id for item in deduped] == ["first", "unique"]


def test_deduplicate_items_retains_items_without_usable_keys() -> None:
    first = {"title": "", "abstract": "", "source_url": ""}
    second = {"title": "", "abstract": "", "source_url": ""}

    assert deduplicate_items([first, second]) == [first, second]
