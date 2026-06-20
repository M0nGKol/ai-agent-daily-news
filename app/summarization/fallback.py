"""Deterministic fallback summarization."""

from __future__ import annotations

import re

from app.summarization.models import DigestSummary, SourceItem
from app.summarization.prompts import UNAVAILABLE
from app.summarization.utils import confidence_category


def build_extractive_fallback_summary(
    source: SourceItem,
    *,
    model_used: str | None = None,
) -> DigestSummary:
    """Build a deterministic summary directly from the source title and abstract."""

    title = source.title or UNAVAILABLE
    if source.abstract:
        extracted = _first_sentences(source.abstract, max_sentences=2)
        summary = extracted or source.abstract
    else:
        summary = f"Source did not provide an abstract; available title: {title}."

    why_it_matters = _fallback_why_it_matters(source)
    score = _fallback_confidence(source)

    return DigestSummary(
        title=title,
        summary=summary,
        why_it_matters=why_it_matters,
        source_url=source.source_url,
        confidence_score=score,
        confidence_category=confidence_category(score),
        source_name=source.source_name,
        source_type=source.source_type,
        model_used=model_used,
        used_fallback=True,
    )


def _fallback_why_it_matters(source: SourceItem) -> str:
    source_text = f"{source.title} {source.abstract}".strip()
    matched_terms = _extract_known_terms(source_text)
    if matched_terms:
        return (
            "Worth watching for teams tracking "
            f"{', '.join(matched_terms[:3])}."
        )
    return "Worth scanning as part of today's AI technology watchlist."


def _fallback_confidence(source: SourceItem) -> float:
    if len(source.abstract) >= 500:
        return 0.78
    if len(source.abstract) >= 160:
        return 0.68
    if source.abstract:
        return 0.55
    return 0.35


def _extract_known_terms(text: str) -> list[str]:
    candidates = (
        "AI",
        "agent",
        "benchmark",
        "dataset",
        "evaluation",
        "GPU",
        "LLM",
        "model",
        "open source",
        "research",
        "robotics",
        "safety",
    )
    lowered = text.lower()
    matched_terms: list[str] = []
    for term in candidates:
        pattern = r"\b" + re.escape(term.lower()).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, lowered):
            matched_terms.append(term)
    return matched_terms


def _first_sentences(text: str, *, max_sentences: int) -> str:
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()
    ]
    if not sentences:
        return ""
    return " ".join(sentences[:max_sentences])
