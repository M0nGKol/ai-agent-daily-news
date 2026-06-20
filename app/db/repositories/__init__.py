"""Database repository package."""

from app.db.repositories.common import init_db
from app.db.repositories.digests import (
    add_digest_item,
    create_daily_digest,
    list_recent_digest_source_urls,
)
from app.db.repositories.sources import (
    get_or_create_source,
    list_recent_items,
    upsert_source_item,
)
from app.db.repositories.topics import (
    create_topic_delivery_plan,
    get_due_topic_delivery,
    mark_topic_delivery_sent,
)

__all__ = [
    "add_digest_item",
    "create_daily_digest",
    "create_topic_delivery_plan",
    "get_due_topic_delivery",
    "get_or_create_source",
    "init_db",
    "list_recent_items",
    "list_recent_digest_source_urls",
    "mark_topic_delivery_sent",
    "upsert_source_item",
]
