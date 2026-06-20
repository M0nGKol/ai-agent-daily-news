"""Application configuration loaded from environment variables and .env files."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_RSS_FEEDS: tuple[str, ...] = (
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss.xml",
    "https://blog.google/technology/ai/rss/",
    "https://deepmind.google/blog/rss.xml",
    "https://www.microsoft.com/en-us/research/feed/",
    "https://developer.nvidia.com/blog/feed/",
    "https://bair.berkeley.edu/blog/feed.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://www.technologyreview.com/feed/",
    "https://venturebeat.com/category/ai/feed/",
)
DEFAULT_SQLITE_DATABASE_URL = "sqlite:///./daily_digest.db"
MAX_DAILY_DIGEST_ITEMS = 5
DEFAULT_GDELT_QUERY = (
    '("artificial intelligence" OR "generative AI" OR '
    '"large language model" OR "AI agent" OR "machine learning")'
)


class Settings(BaseSettings):
    """Runtime settings for the daily digest batch job."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = DEFAULT_SQLITE_DATABASE_URL

    telegram_bot_token: str | None = Field(default=None, repr=False)
    telegram_chat_id: str | None = Field(default=None, repr=False)
    telegram_command_allowed_ids: str = ""
    telegram_digest_command: str = "/digest"
    telegram_command_poll_timeout_seconds: int = 25

    llm_provider: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    llm_base_url: str | None = None

    semantic_scholar_api_key: str | None = Field(default=None, repr=False)

    rss_feeds: str = ",".join(DEFAULT_RSS_FEEDS)
    max_digest_items: int = MAX_DAILY_DIGEST_ITEMS
    http_timeout_seconds: int = 20
    digest_mode: str = "topics"
    source_state_dir: str = "state"
    digest_repeat_lookback_days: int = 14
    max_items_per_source_domain: int = 1
    gdelt_enabled: bool = True
    gdelt_query: str = DEFAULT_GDELT_QUERY
    gdelt_timespan: str = "3d"
    gdelt_max_records: int = 50
    topic_timezone: str = "Asia/Phnom_Penh"
    topic_send_start_hour: int = 8
    topic_send_end_hour: int = 22
    topic_due_window_minutes: int = 75

    @property
    def rss_feed_urls(self) -> list[str]:
        """Return RSS_FEEDS as a cleaned list of feed URLs."""

        return [feed.strip() for feed in self.rss_feeds.split(",") if feed.strip()]

    @field_validator("rss_feeds", mode="before")
    @classmethod
    def blank_rss_feeds_to_defaults(cls, value: Any) -> Any:
        """Use curated AI news feeds when RSS_FEEDS is omitted or blank."""

        if value is None:
            return ",".join(DEFAULT_RSS_FEEDS)
        if isinstance(value, str) and not value.strip():
            return ",".join(DEFAULT_RSS_FEEDS)
        return value

    @field_validator(
        "telegram_bot_token",
        "telegram_chat_id",
        "llm_provider",
        "llm_api_key",
        "llm_model",
        "llm_base_url",
        "semantic_scholar_api_key",
        mode="before",
    )
    @classmethod
    def empty_strings_to_none(cls, value: Any) -> Any:
        """Treat blank optional environment values as missing."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "max_digest_items",
        "http_timeout_seconds",
        "telegram_command_poll_timeout_seconds",
        "topic_due_window_minutes",
        "digest_repeat_lookback_days",
        "max_items_per_source_domain",
        "gdelt_max_records",
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        """Require positive integer limits for batch and HTTP settings."""
        if value <= 0:
            raise ValueError("must be greater than 0")
        return value

    @field_validator("topic_send_start_hour", "topic_send_end_hour")
    @classmethod
    def valid_hour(cls, value: int) -> int:
        """Require hour settings to be valid local wall-clock hours."""
        if value < 0 or value > 23:
            raise ValueError("must be between 0 and 23")
        return value

    @field_validator("max_digest_items")
    @classmethod
    def cap_digest_items(cls, value: int) -> int:
        """Keep the digest compact even when an old .env still requests more."""
        return min(value, MAX_DAILY_DIGEST_ITEMS)


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings from the environment and .env."""

    return Settings()
