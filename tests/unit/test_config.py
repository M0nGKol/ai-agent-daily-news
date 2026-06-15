from __future__ import annotations

from app.config import DEFAULT_RSS_FEEDS, MAX_DAILY_DIGEST_ITEMS, Settings


def test_settings_defaults_to_five_items_and_curated_rss_feeds() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_digest_items == MAX_DAILY_DIGEST_ITEMS
    assert settings.rss_feed_urls == list(DEFAULT_RSS_FEEDS)


def test_blank_rss_feeds_uses_curated_defaults() -> None:
    settings = Settings(rss_feeds="", _env_file=None)

    assert settings.rss_feed_urls == list(DEFAULT_RSS_FEEDS)


def test_max_digest_items_is_capped_at_five() -> None:
    settings = Settings(max_digest_items=10, _env_file=None)

    assert settings.max_digest_items == MAX_DAILY_DIGEST_ITEMS
