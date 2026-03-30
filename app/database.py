"""Database connection and session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def _build_engine():
    """Build the SQLAlchemy engine from DATABASE_URL env var (or config fallback)."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        from app.config import get_settings
        database_url = get_settings().database_url

    kwargs: dict = {}
    if database_url.startswith("postgresql"):
        kwargs = {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}

    return create_engine(database_url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
