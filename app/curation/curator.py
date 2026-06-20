"""Curation: classify, filter for substance, then select with rotation + novelty.

This ties together the two halves of the plan:

* ``classification`` drops hype and maps each kept item to an engineering bucket.
* ``source_discovery`` supplies a dynamic trust map and a novelty bonus.

Selection then scores survivors (ranking + dynamic trust + novelty) and fills the
digest by rotating across buckets so the topic mix and sources stay fresh.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.curation.classification import (
    BucketConfig,
    Classification,
    classify_and_filter,
    get_bucket_config,
)
from app.curation.deduplication import deduplication_keys, item_value, normalize_url
from app.curation.ranking import score_item
from app.curation.source_discovery import (
    SourceRegistry,
    domain_of,
    dynamic_source_trust_map,
    novelty_bonus,
)


@dataclass(frozen=True)
class ScoredItem:
    """An item paired with its classification and final score."""

    item: Any
    classification: Classification
    score: float


@dataclass(frozen=True)
class CurationResult:
    """Outcome of a curation pass."""

    selected: list[Any] = field(default_factory=list)
    bucket_by_url: dict[str, str] = field(default_factory=dict)
    kept_domains: list[str] = field(default_factory=list)
    selected_domains: list[str] = field(default_factory=list)
    dropped_count: int = 0


def curate_items(
    items: Sequence[Any],
    *,
    max_items: int,
    registry: SourceRegistry,
    bucket_config: BucketConfig | None = None,
    now: datetime | None = None,
    max_per_bucket: int | None = None,
    max_per_domain: int | None = None,
) -> CurationResult:
    """Classify, filter, score, and bucket-rotate items into a digest selection."""

    if max_items <= 0:
        return CurationResult()

    config = bucket_config or get_bucket_config()
    materialized = list(items)
    kept = classify_and_filter(materialized, config)
    dropped_count = max(len(materialized) - len(kept), 0)

    if not kept:
        return CurationResult(dropped_count=dropped_count)

    trust_map = dynamic_source_trust_map(registry)
    scored: list[ScoredItem] = []
    kept_domains: list[str] = []
    for item, classification in kept:
        domain = domain_of(item_value(item, "source_url", ""))
        if domain:
            kept_domains.append(domain)
        base = score_item(item, source_trust_map=trust_map, now=now)
        bonus = novelty_bonus(registry, domain, now=now)
        scored.append(ScoredItem(item=item, classification=classification, score=base + bonus))

    scored.sort(key=lambda entry: entry.score, reverse=True)
    deduped = _dedupe_scored(scored)

    selected_entries = _rotate_by_bucket(
        deduped,
        max_items=max_items,
        max_per_bucket=max_per_bucket,
        max_per_domain=max_per_domain,
    )

    selected = [entry.item for entry in selected_entries]
    bucket_by_url = {
        normalize_url(item_value(entry.item, "source_url", "")): (
            entry.classification.bucket or ""
        )
        for entry in selected_entries
    }
    selected_domains = [
        domain
        for entry in selected_entries
        if (domain := domain_of(item_value(entry.item, "source_url", "")))
    ]

    return CurationResult(
        selected=selected,
        bucket_by_url=bucket_by_url,
        kept_domains=_unique(kept_domains),
        selected_domains=_unique(selected_domains),
        dropped_count=dropped_count,
    )


def _dedupe_scored(scored: Iterable[ScoredItem]) -> list[ScoredItem]:
    seen: set[tuple[str, str]] = set()
    unique: list[ScoredItem] = []
    for entry in scored:
        keys = deduplication_keys(entry.item)
        if keys and any(key in seen for key in keys):
            continue
        unique.append(entry)
        seen.update(keys)
    return unique


def _rotate_by_bucket(
    scored: Sequence[ScoredItem],
    *,
    max_items: int,
    max_per_bucket: int | None,
    max_per_domain: int | None,
) -> list[ScoredItem]:
    """Round-robin across buckets (best first) so the mix varies each run."""

    order: list[str] = []
    by_bucket: dict[str, list[ScoredItem]] = {}
    for entry in scored:
        bucket = entry.classification.bucket or "_unbucketed"
        if bucket not in by_bucket:
            by_bucket[bucket] = []
            order.append(bucket)
        by_bucket[bucket].append(entry)

    counts: dict[str, int] = {bucket: 0 for bucket in order}
    domain_counts: dict[str, int] = {}
    selected: list[ScoredItem] = []
    while len(selected) < max_items:
        progressed = False
        for bucket in order:
            queue = by_bucket[bucket]
            while queue:
                if max_per_bucket is not None and counts[bucket] >= max_per_bucket:
                    queue.clear()
                    break
                entry = queue.pop(0)
                domain = domain_of(item_value(entry.item, "source_url", ""))
                if (
                    max_per_domain is not None
                    and domain
                    and domain_counts.get(domain, 0) >= max_per_domain
                ):
                    continue
                selected.append(entry)
                counts[bucket] += 1
                if domain:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                progressed = True
                break
            if len(selected) >= max_items:
                break
        if not progressed:
            break

    return selected


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
