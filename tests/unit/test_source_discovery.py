from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.source_discovery import (
    SourceRegistry,
    demote_stale_sources,
    domain_of,
    dynamic_source_trust_map,
    harvest_candidates,
    load_registry,
    novelty_bonus,
    promote_candidates,
    record_dropped,
    record_posted,
    save_registry,
    seed_trusted,
)


def _item(url: str) -> dict[str, str]:
    return {"source_url": url, "title": "t", "abstract": "a"}


def test_domain_of_strips_scheme_and_www() -> None:
    assert domain_of("https://www.Example.com/a/b?x=1") == "example.com"


def test_seed_trusted_adds_feed_domains() -> None:
    registry = SourceRegistry()
    seed_trusted(registry, ["https://openai.com/news/rss.xml"])
    assert "openai.com" in registry.trusted


def test_harvest_skips_trusted_and_counts_candidates() -> None:
    registry = SourceRegistry(trusted={"openai.com": {"trust_score": 8.0}})
    harvest_candidates(
        registry,
        [_item("https://openai.com/x"), _item("https://newblog.dev/p")],
    )
    harvest_candidates(registry, [_item("https://newblog.dev/q")])
    assert "openai.com" not in registry.candidates
    assert registry.candidates["newblog.dev"]["count"] == 2


def test_promote_after_threshold_appearances() -> None:
    registry = SourceRegistry()
    for _ in range(3):
        harvest_candidates(registry, [_item("https://rising.ai/p")])
    promoted = promote_candidates(registry)
    assert "rising.ai" in promoted
    assert registry.is_trusted("rising.ai")


def test_promote_on_high_signal_even_below_threshold() -> None:
    registry = SourceRegistry()
    harvest_candidates(
        registry,
        [_item("https://signal.dev/p")],
        high_signal_domains=["signal.dev"],
    )
    promoted = promote_candidates(registry)
    assert "signal.dev" in promoted


def test_demote_low_hit_rate_discovered_source() -> None:
    registry = SourceRegistry(
        trusted={"weak.example": {"trust_score": 7.0, "origin": "discovered"}},
        stats={"weak.example": {"posted": 0, "dropped": 8}},
    )
    demoted = demote_stale_sources(registry)
    assert "weak.example" in demoted
    assert "weak.example" not in registry.trusted


def test_seed_sources_are_never_demoted() -> None:
    registry = SourceRegistry(
        trusted={"openai.com": {"trust_score": 8.0, "origin": "seed"}},
        stats={"openai.com": {"posted": 0, "dropped": 50}},
    )
    assert demote_stale_sources(registry) == []
    assert registry.is_trusted("openai.com")


def test_novelty_bonus_full_for_never_posted() -> None:
    registry = SourceRegistry()
    assert novelty_bonus(registry, "fresh.dev", bonus=4.0) == 4.0


def test_novelty_bonus_zero_for_recently_posted() -> None:
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    registry = SourceRegistry(
        stats={"recent.dev": {"last_posted": (now - timedelta(days=2)).isoformat()}}
    )
    assert novelty_bonus(registry, "recent.dev", now=now, window_days=14) == 0.0


def test_novelty_bonus_returns_after_window() -> None:
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    registry = SourceRegistry(
        stats={"old.dev": {"last_posted": (now - timedelta(days=20)).isoformat()}}
    )
    assert novelty_bonus(registry, "old.dev", now=now, window_days=14) == 4.0


def test_record_posted_and_dropped_update_stats() -> None:
    registry = SourceRegistry()
    record_posted(registry, ["https://a.dev/x"])
    record_dropped(registry, ["a.dev", "a.dev"])
    assert registry.stats["a.dev"]["posted"] == 1
    assert registry.stats["a.dev"]["dropped"] == 2


def test_dynamic_trust_map_uses_trust_scores() -> None:
    registry = SourceRegistry(trusted={"a.dev": {"trust_score": 9.0}})
    assert dynamic_source_trust_map(registry)["a.dev"] == 9.0


def test_round_trip_persistence(tmp_path) -> None:
    registry = SourceRegistry(
        trusted={"a.dev": {"trust_score": 8.0}},
        candidates={"b.dev": {"count": 2}},
        stats={"a.dev": {"posted": 1, "dropped": 0}},
    )
    save_registry(registry, tmp_path)
    loaded = load_registry(tmp_path)
    assert loaded.trusted == registry.trusted
    assert loaded.candidates == registry.candidates
    assert loaded.stats == registry.stats


def test_load_missing_state_dir_returns_empty() -> None:
    loaded = load_registry("/nonexistent/path/xyz")
    assert loaded.trusted == {}
    assert loaded.candidates == {}
