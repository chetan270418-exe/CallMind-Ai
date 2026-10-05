"""Database engine + session factory + Base + dependency."""
from __future__ import annotations

from typing import Generator
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _normalize_postgres_url(url: str) -> str:
    """SQLAlchemy 2 prefers the explicit 'postgresql+psycopg://' driver prefix.

    Render and Heroku both hand us 'postgres://' URLs. We rewrite them to the
    psycopg driver, which is the one we ship in requirements.txt.

    NOTE: urlunsplit always re-adds the '://' separator, so the scheme we pass
    in must NOT include it. Passing 'postgresql+psycopg://' produces an invalid
    URL like 'postgresql+psycopg://://user:...'. Use the bare scheme.
    """
    if not url or not url.startswith(("postgres://", "postgresql://")):
        return url
    parts = urlsplit(url)
    return urlunsplit((
        "postgresql+psycopg",
        parts.netloc,
        parts.path,
        parts.query,
        parts.fragment,
    ))


def _build_engine():
    url = get_settings().database_url
    url = _normalize_postgres_url(url)
    # SQLite needs a special connect_args; Postgres does not.
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, ensures close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called at startup."""
    from . import models  # noqa: F401 — register models
    Base.metadata.create_all(bind=engine)