from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False so uvicorn's threadpool can share the engine.
        kwargs["connect_args"] = {"check_same_thread": False}
    elif url.startswith("postgresql+psycopg"):
        # Supabase's pooler (port 6543) is PgBouncer in transaction mode: it
        # can hand two different app connections the same backend session, so
        # a server-side prepared statement name from one collides with
        # another's, raising "prepared statement already exists" -- reads as
        # a boot failure or a randomly-500ing endpoint. psycopg3 auto-prepares
        # after a few executions on a connection object by default; disabling
        # that entirely is the documented fix for a transaction pooler.
        kwargs["connect_args"] = {"prepare_threshold": None}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_all() -> None:
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency. One session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
