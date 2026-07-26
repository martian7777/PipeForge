"""SQLAlchemy engine, session factory, and Base for PipeForge metadata."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# check_same_thread=False so the background job threads can share the SQLite file;
# a busy timeout avoids "database is locked" when a job writes while the API reads.
_connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        """Enable WAL + reasonable durability so concurrent read/write behaves."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Prepare storage and, in development, the schema.

    ``create_all`` is a convenience for local SQLite work: it creates missing tables but
    never alters existing ones, so it cannot apply schema changes. Production sets
    ``PIPEFORGE_AUTO_CREATE_TABLES=false`` and runs ``alembic upgrade head`` instead --
    see ``backend/alembic/`` and docs/DEPLOYMENT.md.
    """
    from . import models  # noqa: F401  (register models on Base)

    settings.ensure_dirs()
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
