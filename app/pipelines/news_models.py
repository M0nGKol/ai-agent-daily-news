"""Result models for the news digest pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectorOutcome:
    """Result of one collector execution."""

    name: str
    item_count: int
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the collector completed without an unhandled exception."""

        return self.error is None


@dataclass(frozen=True)
class DailyDigestRunResult:
    """Structured result for the daily digest job."""

    collected_count: int
    selected_count: int
    summarized_count: int
    persisted_source_count: int
    digest_id: int | None
    delivery_attempted: bool
    delivery_succeeded: bool
    collector_outcomes: tuple[CollectorOutcome, ...]
    errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Return whether the job produced and delivered a digest."""

        return self.summarized_count > 0 and self.delivery_succeeded and not self.errors
