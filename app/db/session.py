"""Database engine and session helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./daily_digest.db"


def get_database_url(database_url: str | None = None) -> str:
    """Return an explicit database URL or read one from app.config settings."""
    if database_url:
        return database_url

    try:
        from app.config import get_settings
    except ImportError:
        return DEFAULT_DATABASE_URL

    configured_url = get_settings().database_url
    if configured_url:
        return normalize_database_url(str(configured_url))
    return DEFAULT_DATABASE_URL


def normalize_database_url(database_url: str) -> str:
    """Normalize common database URL variants to installed SQLAlchemy drivers."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def create_db_engine(database_url: str | None = None, **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine for SQLite locally or PostgreSQL in deploys."""
    resolved_url = normalize_database_url(get_database_url(database_url))
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True, **kwargs}

    if resolved_url.startswith("sqlite"):
        engine_kwargs.setdefault("connect_args", {"check_same_thread": False})

    return create_engine(resolved_url, **engine_kwargs)


engine = create_db_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def create_session_factory(
    database_url: str | None = None,
    *,
    db_engine: Engine | None = None,
) -> sessionmaker[Session]:
    """Create a session factory for the given URL or engine."""
    bind = db_engine or create_db_engine(database_url)
    return sessionmaker(
        bind=bind,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Provide a transactional session scope for scripts and jobs."""
    session_factory = SessionLocal if database_url is None else create_session_factory(database_url)
    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
