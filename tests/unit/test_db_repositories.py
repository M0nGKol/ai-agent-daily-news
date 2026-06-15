from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import SourceItem
from app.db.repositories import upsert_source_item
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
