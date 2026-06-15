"""Database models for collected source items and generated daily digests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(UTC)


class Source(Base):
    """A news, paper, API, or RSS source used by collectors."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("source_type", "name", name="uq_sources_type_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    items: Mapped[list[SourceItem]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class SourceItem(Base):
    """A single collected article, blog post, paper, or release note."""

    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_source_items_source_external_id",
        ),
        UniqueConstraint(
            "content_hash",
            "source_url",
            name="uq_source_items_content_hash_source_url",
        ),
        CheckConstraint("source_url <> ''", name="ck_source_items_source_url_not_empty"),
        Index("ix_source_items_source_url", "source_url"),
        Index("ix_source_items_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    source: Mapped[Source] = relationship(back_populates="items")
    digest_items: Mapped[list[DigestItem]] = relationship(back_populates="source_item")


class DailyDigest(Base):
    """A daily digest generated for a calendar date."""

    __tablename__ = "daily_digests"
    __table_args__ = (
        UniqueConstraint("digest_date", name="uq_daily_digests_digest_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    telegram_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    items: Mapped[list[DigestItem]] = relationship(
        back_populates="daily_digest",
        cascade="all, delete-orphan",
        order_by="DigestItem.item_order",
    )


class DigestItem(Base):
    """A curated item included in a daily digest."""

    __tablename__ = "digest_items"
    __table_args__ = (
        UniqueConstraint(
            "daily_digest_id",
            "source_item_id",
            name="uq_digest_items_digest_source_item",
        ),
        UniqueConstraint(
            "daily_digest_id",
            "source_url",
            name="uq_digest_items_digest_source_url",
        ),
        CheckConstraint("source_url <> ''", name="ck_digest_items_source_url_not_empty"),
        Index("ix_digest_items_source_url", "source_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_digest_id: Mapped[int] = mapped_column(
        ForeignKey("daily_digests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    item_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    daily_digest: Mapped[DailyDigest] = relationship(back_populates="items")
    source_item: Mapped[SourceItem | None] = relationship(back_populates="digest_items")


class TopicDelivery(Base):
    """One scheduled AI learning topic card for a local calendar date."""

    __tablename__ = "topic_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "delivery_date",
            "item_order",
            name="uq_topic_deliveries_date_order",
        ),
        UniqueConstraint(
            "delivery_date",
            "topic_key",
            name="uq_topic_deliveries_date_topic",
        ),
        CheckConstraint("source_url <> ''", name="ck_topic_deliveries_source_url_not_empty"),
        Index("ix_topic_deliveries_delivery_date", "delivery_date"),
        Index("ix_topic_deliveries_scheduled_for", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    try_this: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
