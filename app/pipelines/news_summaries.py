"""Summarization helpers for the news digest pipeline."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.config import Settings
from app.curation import item_value
from app.summarization import DigestSummary, create_summarizer


logger = logging.getLogger(__name__)


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


def _summarizer_config(settings: Settings) -> dict[str, Any]:
    return {
        "LLM_PROVIDER": settings.llm_provider,
        "LLM_API_KEY": settings.llm_api_key,
        "LLM_MODEL": settings.llm_model,
        "LLM_BASE_URL": settings.llm_base_url,
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
