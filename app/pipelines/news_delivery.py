"""Telegram delivery preparation for the news digest pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.curation import item_value, normalize_url
from app.summarization import DigestSummary


def telegram_items_for_summaries(
    summaries: Sequence[DigestSummary],
    selected_items: Sequence[Any],
) -> list[dict[str, Any]]:
    """Attach source metadata and images to summaries for Telegram rendering."""

    selected_by_url = {
        normalize_url(item_value(item, "source_url", "")): item for item in selected_items
    }
    telegram_items: list[dict[str, Any]] = []
    for summary in summaries:
        item = summary_to_telegram_item(summary)
        selected_item = selected_by_url.get(normalize_url(summary.source_url))
        image_url = _clean_text(item_value(selected_item, "image_url", ""))
        if image_url:
            item["image_url"] = image_url
        telegram_items.append(item)
    return telegram_items


def summary_to_telegram_item(summary: DigestSummary) -> dict[str, Any]:
    """Convert a digest summary into Telegram card data."""

    return {
        "title": summary.title,
        "summary": summary.summary,
        "why_it_matters": summary.why_it_matters,
        "source_url": summary.source_url,
        "category": summary.source_name or summary.source_type or "",
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
