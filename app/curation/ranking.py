"""Pure ranking helpers for selecting digest-worthy AI items."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import math
from typing import Any
from urllib.parse import urlparse

from app.curation.deduplication import (
    deduplicate_items,
    item_value,
    normalize_text,
    normalize_url,
)

DEFAULT_KEYWORD_WEIGHTS: dict[str, float] = {
    "agent": 2.0,
    "agents": 2.0,
    "ai": 1.5,
    "alignment": 2.5,
    "artificial intelligence": 3.0,
    "benchmark": 2.0,
    "cuda": 1.5,
    "dataset": 1.5,
    "diffusion": 2.0,
    "embedding": 2.0,
    "eval": 2.0,
    "evaluation": 2.0,
    "fine tuning": 2.0,
    "foundation model": 3.0,
    "generative ai": 3.5,
    "gpu": 1.5,
    "inference": 2.5,
    "large language model": 4.0,
    "llm": 4.0,
    "machine learning": 2.5,
    "mixture of experts": 2.5,
    "model serving": 2.0,
    "multimodal": 2.5,
    "open source model": 2.5,
    "rag": 3.0,
    "reasoning": 2.0,
    "retrieval augmented generation": 3.5,
    "rlhf": 2.5,
    "safety": 1.5,
    "synthetic data": 2.0,
    "tokenizer": 1.5,
    "training": 2.0,
    "transformer": 2.5,
    "vector database": 1.5,
}

DEFAULT_SOURCE_TRUST_SCORES: dict[str, float] = {
    "acl anthology": 8.5,
    "anthropic": 8.0,
    "arxiv": 8.0,
    "arxiv.org": 8.0,
    "blog": 4.5,
    "google ai blog": 8.0,
    "hugging face": 7.5,
    "iclr": 9.0,
    "icml": 9.0,
    "meta ai": 7.5,
    "microsoft research": 8.0,
    "mit technology review": 7.5,
    "nature": 9.0,
    "neurips": 9.0,
    "news": 4.0,
    "openai": 8.0,
    "openreview": 8.5,
    "paper": 7.0,
    "research": 7.0,
    "rss": 4.0,
    "science": 9.0,
    "semianalysis": 7.5,
}

DEFAULT_SOURCE_TRUST_SCORE = 4.0
DEFAULT_MAX_ITEMS = 10
DEFAULT_RECENCY_HALF_LIFE_HOURS = 36.0
DEFAULT_RECENCY_MAX_SCORE = 10.0
KEYWORD_TITLE_MULTIPLIER = 1.6
KEYWORD_MAX_SCORE = 40.0


@dataclass(frozen=True)
class RankingScore:
    """Score components for one item."""

    keyword: float
    recency: float
    source_trust: float

    @property
    def total(self) -> float:
        """Combined score used for sorting."""
        return self.keyword + self.recency + self.source_trust


def keyword_score(
    item: Any,
    keyword_weights: Mapping[str, float] | None = None,
) -> float:
    """Score an item for AI research and engineering relevance."""
    weights = keyword_weights or DEFAULT_KEYWORD_WEIGHTS
    title = item_value(item, "title", "")
    abstract = item_value(item, "abstract", "")

    score = (
        _keyword_text_score(title, weights) * KEYWORD_TITLE_MULTIPLIER
        + _keyword_text_score(abstract, weights)
    )
    return min(score, KEYWORD_MAX_SCORE)


def recency_score(
    item: Any,
    *,
    now: datetime | None = None,
    half_life_hours: float = DEFAULT_RECENCY_HALF_LIFE_HOURS,
    max_score: float = DEFAULT_RECENCY_MAX_SCORE,
) -> float:
    """Score recency using exponential decay from the published timestamp."""
    published_at = parse_datetime(item_value(item, "published_at", None))
    if published_at is None or half_life_hours <= 0:
        return 0.0

    current_time = _aware_datetime(now or datetime.now(timezone.utc))
    age_seconds = max((current_time - published_at).total_seconds(), 0.0)
    age_hours = age_seconds / 3600
    return max_score * math.pow(0.5, age_hours / half_life_hours)


def source_trust_score(
    item: Any,
    source_trust_map: Mapping[str, float] | None = None,
    *,
    default_score: float = DEFAULT_SOURCE_TRUST_SCORE,
) -> float:
    """Score the source using a configurable trust map."""
    trust_scores = _source_trust_scores(source_trust_map)
    for source_key in _source_keys(item):
        if source_key in trust_scores:
            return trust_scores[source_key]

    return default_score


def score_item_breakdown(
    item: Any,
    *,
    keyword_weights: Mapping[str, float] | None = None,
    source_trust_map: Mapping[str, float] | None = None,
    now: datetime | None = None,
) -> RankingScore:
    """Return keyword, recency, and source-trust score components."""
    return RankingScore(
        keyword=keyword_score(item, keyword_weights),
        recency=recency_score(item, now=now),
        source_trust=source_trust_score(item, source_trust_map),
    )


def score_item(
    item: Any,
    *,
    keyword_weights: Mapping[str, float] | None = None,
    source_trust_map: Mapping[str, float] | None = None,
    now: datetime | None = None,
) -> float:
    """Return the combined ranking score for one item."""
    return score_item_breakdown(
        item,
        keyword_weights=keyword_weights,
        source_trust_map=source_trust_map,
        now=now,
    ).total


def rank_items(
    items: Iterable[Any],
    *,
    keyword_weights: Mapping[str, float] | None = None,
    source_trust_map: Mapping[str, float] | None = None,
    now: datetime | None = None,
    deduplicate: bool = True,
    require_source_url: bool = True,
) -> list[Any]:
    """Return candidate items sorted from highest to lowest ranking score."""
    candidates = [
        item
        for item in items
        if not require_source_url or normalize_url(item_value(item, "source_url", ""))
    ]
    ranked_candidates = sorted(
        (
            (
                index,
                item,
                score_item(
                    item,
                    keyword_weights=keyword_weights,
                    source_trust_map=source_trust_map,
                    now=now,
                ),
                _published_timestamp(item),
            )
            for index, item in enumerate(candidates)
        ),
        key=lambda row: (row[2], row[3], -row[0]),
        reverse=True,
    )
    ranked_items_list = [item for _, item, _, _ in ranked_candidates]

    if deduplicate:
        return deduplicate_items(ranked_items_list)

    return ranked_items_list


def select_top_items(
    items: Iterable[Any],
    *,
    max_items: int = DEFAULT_MAX_ITEMS,
    keyword_weights: Mapping[str, float] | None = None,
    source_trust_map: Mapping[str, float] | None = None,
    now: datetime | None = None,
    deduplicate: bool = True,
    require_source_url: bool = True,
) -> list[Any]:
    """Return the top ranked items, limited by max_items."""
    if max_items <= 0:
        return []

    return rank_items(
        items,
        keyword_weights=keyword_weights,
        source_trust_map=source_trust_map,
        now=now,
        deduplicate=deduplicate,
        require_source_url=require_source_url,
    )[:max_items]


def parse_datetime(value: Any) -> datetime | None:
    """Parse common datetime values into timezone-aware UTC datetimes."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return _aware_datetime(value)

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"

        try:
            return _aware_datetime(datetime.fromisoformat(text))
        except ValueError:
            return None

    return None


def _keyword_text_score(
    text: Any,
    keyword_weights: Mapping[str, float],
) -> float:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return 0.0

    searchable_text = f" {normalized_text} "
    total = 0.0
    for keyword, weight in keyword_weights.items():
        normalized_keyword = normalize_text(keyword)
        if not normalized_keyword:
            continue

        count = searchable_text.count(f" {normalized_keyword} ")
        total += min(count, 3) * weight

    return total


def _source_trust_scores(
    source_trust_map: Mapping[str, float] | None,
) -> dict[str, float]:
    scores = {
        normalize_text(key): value for key, value in DEFAULT_SOURCE_TRUST_SCORES.items()
    }
    if source_trust_map:
        scores.update(
            {normalize_text(key): value for key, value in source_trust_map.items()}
        )

    return scores


def _source_keys(item: Any) -> list[str]:
    keys: list[str] = []
    for field_name in ("source_name", "source_type"):
        normalized = normalize_text(item_value(item, field_name, ""))
        if normalized:
            keys.append(normalized)

    domain = _domain_from_url(item_value(item, "source_url", ""))
    if domain:
        keys.append(domain)
        keys.append(normalize_text(domain))

    return keys


def _domain_from_url(url: Any) -> str:
    normalized_url = normalize_url(url)
    if not normalized_url:
        return ""

    host = urlparse(normalized_url).netloc
    return host[4:] if host.startswith("www.") else host


def _published_timestamp(item: Any) -> float:
    published_at = parse_datetime(item_value(item, "published_at", None))
    return published_at.timestamp() if published_at else 0.0


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)
