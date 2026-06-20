from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import SourceItem
from app.db.repositories import (
    add_digest_item,
    create_daily_digest,
    list_recent_digest_source_urls,
    upsert_source_item,
)
from app.db.session import normalize_database_url


def test_normalize_database_url_uses_installed_psycopg_driver() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@example.com:5432/db")
        == "postgresql+psycopg://user:pass@example.com:5432/db"
    )
    assert (
        normalize_database_url("postgres://user:pass@example.com:5432/db")
        == "postgresql+psycopg://user:pass@example.com:5432/db"
    )
    assert normalize_database_url("sqlite:///./daily_digest.db") == "sqlite:///./daily_digest.db"


def test_upsert_source_item_keeps_same_content_from_different_urls() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        first = upsert_source_item(
            db,
            source_type="rss",
            source_name="Feed A",
            title="Shared AI title",
            abstract="Shared source text about AI systems.",
            source_url="https://example.com/a",
            external_id="a",
        )
        second = upsert_source_item(
            db,
            source_type="rss",
            source_name="Feed B",
            title="Shared AI title",
            abstract="Shared source text about AI systems.",
            source_url="https://example.com/b",
            external_id="b",
        )

        assert first.id != second.id
        urls = {item.source_url for item in db.scalars(select(SourceItem))}
        assert urls == {"https://example.com/a", "https://example.com/b"}


def test_list_recent_digest_source_urls_returns_sent_digest_urls() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        sent_digest = create_daily_digest(
            db,
            digest_date=date(2026, 6, 16),
            status="sent",
        )
        draft_digest = create_daily_digest(
            db,
            digest_date=date(2026, 6, 15),
            status="ready",
        )
        old_digest = create_daily_digest(
            db,
            digest_date=date(2026, 5, 1),
            status="sent",
        )
        add_digest_item(
            db,
            daily_digest=sent_digest,
            title="Sent",
            summary="Sent summary",
            source_url="https://example.com/sent",
        )
        add_digest_item(
            db,
            daily_digest=draft_digest,
            title="Draft",
            summary="Draft summary",
            source_url="https://example.com/draft",
        )
        add_digest_item(
            db,
            daily_digest=old_digest,
            title="Old",
            summary="Old summary",
            source_url="https://example.com/old",
        )
        db.commit()

        assert list_recent_digest_source_urls(
            db,
            since=date(2026, 6, 1),
            sent_only=True,
        ) == {"https://example.com/sent"}
        assert list_recent_digest_source_urls(
            db,
            since=date(2026, 6, 1),
            sent_only=False,
        ) == {"https://example.com/sent", "https://example.com/draft"}
