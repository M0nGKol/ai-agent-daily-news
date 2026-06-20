"""Prompt builders for grounded source summaries."""

from __future__ import annotations

from app.summarization.models import SourceItem

UNAVAILABLE = "Not available in source."


def build_source_grounded_prompt(source: SourceItem) -> str:
    """Build a safe prompt that constrains the model to provided source fields."""

    authors = ", ".join(source.authors) if source.authors else UNAVAILABLE
    return (
        "Summarize this single source for a daily AI technology digest.\n"
        "Rules:\n"
        "- Use only the source fields below; do not add outside facts.\n"
        f"- Include this exact source_url in the JSON: {source.source_url}\n"
        f"- If a detail is unavailable, say \"{UNAVAILABLE}\"\n"
        "- Keep summary to 1-2 concise sentences.\n"
        "- Keep why_it_matters to 1 concise sentence grounded in the source.\n"
        "- Return JSON with keys: title, summary, why_it_matters, source_url, "
        "confidence_score.\n\n"
        f"title: {source.title or UNAVAILABLE}\n"
        f"abstract: {source.abstract or UNAVAILABLE}\n"
        f"authors: {authors}\n"
        f"published_at: {source.published_at or UNAVAILABLE}\n"
        f"source_name: {source.source_name or UNAVAILABLE}\n"
        f"source_type: {source.source_type or UNAVAILABLE}\n"
        f"source_url: {source.source_url}\n"
    )
