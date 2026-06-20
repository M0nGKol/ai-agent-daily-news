from __future__ import annotations

from app.schemas.items import CollectedItem
from app.curation.classification import (
    classify_and_filter,
    classify_item,
    get_bucket_config,
)


def _item(title: str, abstract: str = "") -> CollectedItem:
    return CollectedItem(
        source_type="rss",
        source_name="Example",
        external_id=title,
        title=title,
        abstract=abstract,
        authors=[],
        published_at=None,
        source_url="https://example.com/post",
    )


def test_serving_item_maps_to_serving_bucket() -> None:
    result = classify_item(
        _item("vLLM adds speculative decoding for faster inference throughput")
    )
    assert result.kept is True
    assert result.bucket == "serving_inference"


def test_rag_item_maps_to_rag_bucket() -> None:
    result = classify_item(
        _item("A guide to rerankers and hybrid search for RAG retrieval pipelines")
    )
    assert result.kept is True
    assert result.bucket == "rag_retrieval"


def test_funding_headline_is_dropped_as_hype() -> None:
    result = classify_item(
        _item("AI startup raises $200M Series B at a $2B valuation")
    )
    assert result.kept is False
    assert result.reason == "hype_title"


def test_non_engineering_item_without_bucket_is_dropped() -> None:
    result = classify_item(
        _item("The philosophy of consciousness and what it means for society")
    )
    assert result.kept is False
    assert result.bucket is None


def test_hype_title_dropped_even_with_engineering_keyword() -> None:
    # Contains "inference" but is fundamentally an acquisition announcement.
    result = classify_item(
        _item("Big Corp acquires inference startup in cash-and-stock deal")
    )
    assert result.kept is False
    assert result.reason == "hype_title"


def test_classify_and_filter_keeps_only_in_scope_items() -> None:
    items = [
        _item("New LoRA fine-tuning recipe with QLoRA and DPO"),
        _item("Company hires new CEO to lead growth"),
        _item("Open-source agent framework adds tool calling and MCP support"),
    ]
    kept = classify_and_filter(items)
    kept_titles = {item.title for item, _ in kept}
    assert "Company hires new CEO to lead growth" not in kept_titles
    assert len(kept) == 2


def test_bucket_config_has_six_buckets() -> None:
    config = get_bucket_config()
    assert len(config.buckets) == 6
