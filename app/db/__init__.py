"""Database package exports."""

from app.db.base import Base
from app.db.models import DailyDigest, DigestItem, Source, SourceItem, TopicDelivery
from app.db.repositories import (
    add_digest_item,
    create_daily_digest,
    create_topic_delivery_plan,
    get_due_topic_delivery,
    get_or_create_source,
    init_db,
    list_recent_items,
    mark_topic_delivery_sent,
    upsert_source_item,
)
from app.db.session import (
    DEFAULT_DATABASE_URL,
    SessionLocal,
    create_db_engine,
    create_session_factory,
    engine,
    get_database_url,
    session_scope,
)

__all__ = [
    "DEFAULT_DATABASE_URL",
    "Base",
    "DailyDigest",
    "DigestItem",
    "SessionLocal",
    "Source",
    "SourceItem",
    "TopicDelivery",
    "add_digest_item",
    "create_daily_digest",
    "create_topic_delivery_plan",
    "create_db_engine",
    "create_session_factory",
    "engine",
    "get_due_topic_delivery",
    "get_database_url",
    "get_or_create_source",
    "init_db",
    "list_recent_items",
    "mark_topic_delivery_sent",
    "session_scope",
    "upsert_source_item",
]
