"""Source-grounded summarization service."""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.summarization.fact_checking import ensure_publishable_summary, validate_source_item
from app.summarization.fallback import build_extractive_fallback_summary
from app.summarization.llm_client import build_configured_llm_client
from app.summarization.models import DigestSummary, LLMClient, SourceItem
from app.summarization.prompts import UNAVAILABLE, build_source_grounded_prompt
from app.summarization.utils import (
    clean_text,
    coerce_score,
    confidence_category,
    extract_json_object,
    normalize_authors,
    normalize_published_at,
    read_config_value,
    read_field,
)


class SourceGroundedSummarizer:
    """Summarize source items with an optional LLM and deterministic fallback."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        model_used: str | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.model_used = model_used

    def summarize(self, item: Mapping[str, Any] | object) -> DigestSummary:
        """Create a validated digest summary for a single source item."""

        source = normalize_source_item(item)
        source_validation = validate_source_item(source)
        if not source_validation.passed:
            details = "; ".join(issue.message for issue in source_validation.issues)
            raise ValueError(f"Source item failed validation: {details}")

        if self.llm_client is not None:
            try:
                prompt = build_source_grounded_prompt(source)
                summary = self._summary_from_llm_text(source, self.llm_client.complete(prompt))
                ensure_publishable_summary(summary, source)
                return summary
            except (RuntimeError, ValueError, json.JSONDecodeError, TypeError):
                pass

        summary = build_extractive_fallback_summary(source, model_used=self.model_used)
        ensure_publishable_summary(summary, source)
        return summary

    def _summary_from_llm_text(self, source: SourceItem, raw_text: str) -> DigestSummary:
        data = json.loads(extract_json_object(raw_text))
        summary = clean_text(data.get("summary")) or UNAVAILABLE
        why_it_matters = clean_text(data.get("why_it_matters")) or UNAVAILABLE
        score = coerce_score(data.get("confidence_score"), default=0.75)
        category = confidence_category(score)

        return DigestSummary(
            title=clean_text(data.get("title")) or source.title,
            summary=summary,
            why_it_matters=why_it_matters,
            source_url=source.source_url,
            confidence_score=score,
            confidence_category=category,
            source_name=source.source_name,
            source_type=source.source_type,
            model_used=self.model_used,
            used_fallback=False,
        )


def summarize_item(
    item: Mapping[str, Any] | object,
    *,
    llm_client: LLMClient | None = None,
    config: Mapping[str, Any] | object | None = None,
) -> DigestSummary:
    """Summarize one source item, using a configured LLM only when available."""

    summarizer = create_summarizer(llm_client=llm_client, config=config)
    return summarizer.summarize(item)


def create_summarizer(
    *,
    llm_client: LLMClient | None = None,
    config: Mapping[str, Any] | object | None = None,
) -> SourceGroundedSummarizer:
    """Build a summarizer with an injected client or configured HTTP client."""

    if llm_client is not None:
        model_used = read_config_value(config, "LLM_MODEL") if config is not None else None
        return SourceGroundedSummarizer(llm_client=llm_client, model_used=model_used)

    configured_client = build_configured_llm_client(config)
    return SourceGroundedSummarizer(
        llm_client=configured_client,
        model_used=configured_client.model if configured_client is not None else None,
    )


def normalize_source_item(item: Mapping[str, Any] | object) -> SourceItem:
    """Normalize mapping or object source records into the service input model."""

    authors = normalize_authors(read_field(item, "authors"))
    published_at = normalize_published_at(read_field(item, "published_at"))
    source_name = read_field(item, "source_name") or read_field(item, "source")

    return SourceItem(
        title=clean_text(read_field(item, "title")),
        abstract=clean_text(read_field(item, "abstract")),
        authors=authors,
        published_at=published_at,
        source_url=clean_text(read_field(item, "source_url")),
        source_name=clean_text(source_name) or None,
        source_type=clean_text(read_field(item, "source_type")) or None,
    )
