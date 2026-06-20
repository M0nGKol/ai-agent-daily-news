"""Data models and protocols for source-grounded summarization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol


class LLMClient(Protocol):
    """Minimal LLM interface so tests can inject a fake completion client."""

    def complete(self, prompt: str) -> str:
        """Return model text for a prepared prompt."""


@dataclass(frozen=True)
class SourceItem:
    """Normalized source data used by summarization and fact checking."""

    title: str
    source_url: str
    abstract: str = ""
    authors: tuple[str, ...] = ()
    published_at: str | None = None
    source_name: str | None = None
    source_type: str | None = None


@dataclass(frozen=True)
class DigestSummary:
    """A publishable, source-linked summary for the daily digest."""

    title: str
    summary: str
    why_it_matters: str
    source_url: str
    confidence_score: float
    confidence_category: str
    source_name: str | None = None
    source_type: str | None = None
    model_used: str | None = None
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation for rendering or persistence."""

        return asdict(self)


class Summarizer(Protocol):
    """Minimal summarization interface for mocking service-level behavior."""

    def summarize(self, item: Mapping[str, Any] | object) -> DigestSummary:
        """Create a digest summary for one source item."""
