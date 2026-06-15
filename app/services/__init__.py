"""Service helpers for digest item ranking and deduplication."""

from app.services.deduplication import (
    content_hash,
    deduplicate_items,
    deduplication_keys,
    normalize_text,
    normalize_title,
    normalize_url,
)
from app.services.ranking import (
    DEFAULT_KEYWORD_WEIGHTS,
    DEFAULT_SOURCE_TRUST_SCORES,
    RankingScore,
    keyword_score,
    rank_items,
    recency_score,
    score_item,
    score_item_breakdown,
    select_top_items,
    source_trust_score,
)

__all__ = [
    "DEFAULT_KEYWORD_WEIGHTS",
    "DEFAULT_SOURCE_TRUST_SCORES",
    "RankingScore",
    "content_hash",
    "deduplicate_items",
    "deduplication_keys",
    "keyword_score",
    "normalize_text",
    "normalize_title",
    "normalize_url",
    "rank_items",
    "recency_score",
    "score_item",
    "score_item_breakdown",
    "select_top_items",
    "source_trust_score",
]
