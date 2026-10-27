"""SQLite engine (RISKS E8: WAL, busy timeout, short sessions, check_same_thread=False)."""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

BUSY_TIMEOUT_MS = 5000


@lru_cache
def get_engine() -> Engine:
    url = get_settings().sqlite_url
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_MS / 1000} if is_sqlite else {},
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


def reset_engine() -> None:
    """Tests point DATABASE_URL at a temp file and call this."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()


def init_db() -> None:
    """Create all tables."""
    from app.models import tables  # noqa: F401  (registers the tables on SQLModel.metadata)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Keep sessions short: open, do one write per transaction, close."""
    with Session(get_engine()) as session:
        yield session
