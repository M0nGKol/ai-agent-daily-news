"""Bucket classification and substance-vs-hype filtering for digest items.

The goal of the digest is *learning the craft of AI engineering*. Every item must
map to one of a fixed set of engineering buckets; if it cannot, it is treated as
hype and dropped. A small set of "hard hype" phrases (funding, hires, lawsuits,
partnerships) drop an item even when an engineering keyword happens to appear.

These helpers are pure and deterministic so they are easy to unit test.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.curation.deduplication import item_value, normalize_text

BUCKETS_PATH = Path(__file__).resolve().parent.parent / "content" / "buckets.json"

DEFAULT_MIN_BUCKET_SCORE = 1.0
DEFAULT_TITLE_MULTIPLIER = 1.5


@dataclass(frozen=True)
class BucketConfig:
    """Loaded bucket keyword configuration."""

    buckets: dict[str, tuple[str, ...]]
    labels: dict[str, str]
    hype_terms: tuple[str, ...]
    min_bucket_score: float = DEFAULT_MIN_BUCKET_SCORE
    title_multiplier: float = DEFAULT_TITLE_MULTIPLIER


@dataclass(frozen=True)
class Classification:
    """Result of classifying a single item."""

    bucket: str | None
    label: str | None
    score: float
    kept: bool
    reason: str
    bucket_scores: dict[str, float] = field(default_factory=dict)


def load_bucket_config(path: Path | str | None = None) -> BucketConfig:
    """Load and parse the bucket configuration JSON."""

    config_path = Path(path) if path is not None else BUCKETS_PATH
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return _parse_bucket_config(data)


@lru_cache(maxsize=1)
def get_bucket_config() -> BucketConfig:
    """Return the cached default bucket configuration."""

    return load_bucket_config()


def classify_item(
    item: Any,
    config: BucketConfig | None = None,
) -> Classification:
    """Classify one item into an engineering bucket or drop it as hype."""

    bucket_config = config or get_bucket_config()
    title = normalize_text(item_value(item, "title", ""))
    abstract = normalize_text(item_value(item, "abstract", ""))

    # Hard hype guard: announcement-style titles are dropped outright.
    if _contains_any(title, bucket_config.hype_terms):
        return Classification(
            bucket=None,
            label=None,
            score=0.0,
            kept=False,
            reason="hype_title",
        )

    bucket_scores = _score_buckets(title, abstract, bucket_config)
    if not bucket_scores:
        return Classification(
            bucket=None,
            label=None,
            score=0.0,
            kept=False,
            reason="no_bucket",
            bucket_scores={},
        )

    best_bucket = max(bucket_scores, key=lambda key: bucket_scores[key])
    best_score = bucket_scores[best_bucket]

    if best_score < bucket_config.min_bucket_score:
        return Classification(
            bucket=None,
            label=None,
            score=best_score,
            kept=False,
            reason="below_threshold",
            bucket_scores=bucket_scores,
        )

    return Classification(
        bucket=best_bucket,
        label=bucket_config.labels.get(best_bucket, best_bucket),
        score=best_score,
        kept=True,
        reason="matched",
        bucket_scores=bucket_scores,
    )


def classify_and_filter(
    items: Iterable[Any],
    config: BucketConfig | None = None,
) -> list[tuple[Any, Classification]]:
    """Return only kept items paired with their classification."""

    bucket_config = config or get_bucket_config()
    kept: list[tuple[Any, Classification]] = []
    for item in items:
        result = classify_item(item, bucket_config)
        if result.kept:
            kept.append((item, result))
    return kept


def _score_buckets(
    title: str,
    abstract: str,
    config: BucketConfig,
) -> dict[str, float]:
    padded_title = f" {title} "
    padded_abstract = f" {abstract} "
    scores: dict[str, float] = {}

    for bucket, keywords in config.buckets.items():
        score = 0.0
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            if not normalized_keyword:
                continue
            needle = f" {normalized_keyword} "
            title_hits = min(padded_title.count(needle), 2)
            abstract_hits = min(padded_abstract.count(needle), 2)
            score += title_hits * config.title_multiplier + abstract_hits
        if score > 0:
            scores[bucket] = round(score, 4)

    return scores


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    padded = f" {text} "
    for phrase in phrases:
        normalized = normalize_text(phrase)
        if normalized and f" {normalized} " in padded:
            return True
    return False


def _parse_bucket_config(data: Mapping[str, Any]) -> BucketConfig:
    raw_buckets = data.get("buckets", {})
    buckets: dict[str, tuple[str, ...]] = {}
    labels: dict[str, str] = {}
    for key, value in raw_buckets.items():
        if isinstance(value, Mapping):
            keywords = value.get("keywords", [])
            labels[key] = str(value.get("label", key))
        else:
            keywords = value
            labels[key] = key
        buckets[key] = tuple(
            str(keyword) for keyword in keywords if str(keyword).strip()
        )

    hype_terms = tuple(
        str(term) for term in data.get("hype_terms", []) if str(term).strip()
    )
    min_score = float(data.get("min_bucket_score", DEFAULT_MIN_BUCKET_SCORE))
    title_multiplier = float(data.get("title_multiplier", DEFAULT_TITLE_MULTIPLIER))

    return BucketConfig(
        buckets=buckets,
        labels=labels,
        hype_terms=hype_terms,
        min_bucket_score=min_score,
        title_multiplier=title_multiplier,
    )
