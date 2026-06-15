"""Dynamic source discovery: a self-expanding allowlist with a trust gate.

Sources are *where* we look; items are *what* we find. Instead of a hand-edited
allowlist, the source pool grows itself:

1. Harvest candidate domains from every collected item.
2. Pool them (with a counter) rather than trusting immediately.
3. Promote a candidate to ``trusted`` once it appears enough times or produces a
   high-signal (kept/posted) item.
4. Demote a trusted source that consistently produces dropped items.

Two freshness controls sit on top: a novelty bonus for sources not posted
recently, and (in selection) bucket rotation. State persists as small JSON files
so the pool breathes across runs without a database.

All functions are pure-ish and side effects are confined to ``load_registry`` /
``save_registry`` so the logic is easy to unit test.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.deduplication import item_value, normalize_url

DEFAULT_STATE_DIR = Path("state")
TRUSTED_FILE = "trusted_sources.json"
CANDIDATE_FILE = "candidate_sources.json"
STATS_FILE = "source_stats.json"

PROMOTE_AFTER_APPEARANCES = 3
PROMOTE_TRUST_SCORE = 7.0
SEED_TRUST_SCORE = 8.0
DISCOVERED_TRUST_SCORE = 7.0
DEMOTE_MIN_SAMPLES = 5
DEMOTE_MAX_HIT_RATE = 0.15
NOVELTY_WINDOW_DAYS = 14
NOVELTY_BONUS = 4.0


@dataclass
class SourceRegistry:
    """In-memory view of the dynamic source pool."""

    trusted: dict[str, dict[str, Any]] = field(default_factory=dict)
    candidates: dict[str, dict[str, Any]] = field(default_factory=dict)
    stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    def is_trusted(self, domain: str) -> bool:
        return domain in self.trusted


def domain_of(url: Any) -> str:
    """Return a normalized registrable host for a URL (no scheme, no www)."""

    normalized = normalize_url(url)
    if not normalized:
        return ""
    host = urlparse(normalized).netloc
    return host[4:] if host.startswith("www.") else host


def load_registry(state_dir: Path | str = DEFAULT_STATE_DIR) -> SourceRegistry:
    """Load registry JSON files, tolerating missing or malformed files."""

    directory = Path(state_dir)
    return SourceRegistry(
        trusted=_read_json(directory / TRUSTED_FILE),
        candidates=_read_json(directory / CANDIDATE_FILE),
        stats=_read_json(directory / STATS_FILE),
    )


def save_registry(
    registry: SourceRegistry,
    state_dir: Path | str = DEFAULT_STATE_DIR,
) -> None:
    """Persist registry JSON files, creating the directory if needed."""

    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _write_json(directory / TRUSTED_FILE, registry.trusted)
    _write_json(directory / CANDIDATE_FILE, registry.candidates)
    _write_json(directory / STATS_FILE, registry.stats)


def seed_trusted(
    registry: SourceRegistry,
    domains: Iterable[str],
    *,
    trust_score: float = SEED_TRUST_SCORE,
) -> SourceRegistry:
    """Add seed domains to the trusted set if not already present."""

    for raw in domains:
        domain = domain_of(raw) or _bare_domain(raw)
        if not domain or domain in registry.trusted:
            continue
        registry.trusted[domain] = {"trust_score": trust_score, "origin": "seed"}
    return registry


def harvest_candidates(
    registry: SourceRegistry,
    items: Iterable[Any],
    *,
    now: datetime | None = None,
    high_signal_domains: Iterable[str] | None = None,
) -> SourceRegistry:
    """Record domains seen this run as trust-gated candidates.

    Already-trusted domains are skipped. Domains flagged as high-signal (e.g. they
    produced a kept item) get their ``last_high_signal`` timestamp refreshed.
    """

    timestamp = _aware(now).isoformat()
    high_signal = {
        domain_of(domain) or _bare_domain(domain) for domain in (high_signal_domains or [])
    }

    for item in items:
        domain = domain_of(item_value(item, "source_url", ""))
        if not domain or domain in registry.trusted:
            continue

        entry = registry.candidates.setdefault(
            domain,
            {"count": 0, "first_seen": timestamp, "last_high_signal": None},
        )
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_seen"] = timestamp
        if domain in high_signal:
            entry["last_high_signal"] = timestamp

    return registry


def promote_candidates(
    registry: SourceRegistry,
    *,
    appearances_threshold: int = PROMOTE_AFTER_APPEARANCES,
    trust_score: float = PROMOTE_TRUST_SCORE,
) -> list[str]:
    """Promote candidates with enough appearances or a high-signal hit."""

    promoted: list[str] = []
    for domain, entry in list(registry.candidates.items()):
        count = int(entry.get("count", 0))
        had_high_signal = bool(entry.get("last_high_signal"))
        if count >= appearances_threshold or had_high_signal:
            registry.trusted[domain] = {
                "trust_score": trust_score,
                "origin": "discovered",
            }
            registry.candidates.pop(domain, None)
            promoted.append(domain)
    return promoted


def demote_stale_sources(
    registry: SourceRegistry,
    *,
    min_samples: int = DEMOTE_MIN_SAMPLES,
    max_hit_rate: float = DEMOTE_MAX_HIT_RATE,
) -> list[str]:
    """Demote discovered sources whose posted/seen hit rate is consistently poor.

    Seed sources are never demoted; they are the trusted backbone.
    """

    demoted: list[str] = []
    for domain, meta in list(registry.trusted.items()):
        if meta.get("origin") == "seed":
            continue
        stat = registry.stats.get(domain)
        if not stat:
            continue
        posted = int(stat.get("posted", 0))
        dropped = int(stat.get("dropped", 0))
        total = posted + dropped
        if total < min_samples:
            continue
        if (posted / total) <= max_hit_rate:
            registry.trusted.pop(domain, None)
            registry.candidates[domain] = {
                "count": 1,
                "first_seen": _aware(None).isoformat(),
                "last_high_signal": None,
                "demoted": True,
            }
            demoted.append(domain)
    return demoted


def record_posted(
    registry: SourceRegistry,
    domains: Iterable[str],
    *,
    now: datetime | None = None,
) -> SourceRegistry:
    """Increment the posted counter and last_posted timestamp for domains."""

    timestamp = _aware(now).isoformat()
    for raw in domains:
        domain = domain_of(raw) or _bare_domain(raw)
        if not domain:
            continue
        stat = registry.stats.setdefault(domain, {"posted": 0, "dropped": 0})
        stat["posted"] = int(stat.get("posted", 0)) + 1
        stat["last_posted"] = timestamp
    return registry


def record_dropped(
    registry: SourceRegistry,
    domains: Iterable[str],
) -> SourceRegistry:
    """Increment the dropped counter for domains."""

    for raw in domains:
        domain = domain_of(raw) or _bare_domain(raw)
        if not domain:
            continue
        stat = registry.stats.setdefault(domain, {"posted": 0, "dropped": 0})
        stat["dropped"] = int(stat.get("dropped", 0)) + 1
    return registry


def novelty_bonus(
    registry: SourceRegistry,
    domain: str,
    *,
    now: datetime | None = None,
    window_days: int = NOVELTY_WINDOW_DAYS,
    bonus: float = NOVELTY_BONUS,
) -> float:
    """Return a freshness bonus for sources not posted within the window.

    Never-posted sources get the full bonus; recently-posted sources get none, so
    the digest rotates instead of featuring the same handful of sources.
    """

    normalized = domain_of(domain) or _bare_domain(domain)
    if not normalized:
        return 0.0

    stat = registry.stats.get(normalized)
    last_posted = stat.get("last_posted") if stat else None
    if not last_posted:
        return bonus

    last_dt = _parse_iso(last_posted)
    if last_dt is None:
        return bonus

    age_days = (_aware(now) - last_dt).total_seconds() / 86400.0
    return bonus if age_days >= window_days else 0.0


def dynamic_source_trust_map(registry: SourceRegistry) -> dict[str, float]:
    """Build a domain -> trust-score map for the ranking service."""

    trust_map: dict[str, float] = {}
    for domain, meta in registry.trusted.items():
        try:
            trust_map[domain] = float(meta.get("trust_score", DISCOVERED_TRUST_SCORE))
        except (TypeError, ValueError):
            trust_map[domain] = DISCOVERED_TRUST_SCORE
    return trust_map


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def _bare_domain(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text or "/" in text or " " in text:
        return ""
    return text[4:] if text.startswith("www.") else text


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return _aware(datetime.fromisoformat(text))
    except ValueError:
        return None
