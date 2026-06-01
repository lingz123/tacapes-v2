"""Postgres-backed persistence for the dashboard."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _engine_for(url: str | None = None) -> Engine:
    return create_engine(
        url or os.environ["DATABASE_URL"], pool_pre_ping=True, future=True
    )


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> None:
    """Configure the module-level engine + session factory. Idempotent."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = _engine_for(url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yields a transactional session. Commits on success, rolls back on error."""
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    return _engine


__all__ = ["init_engine", "session_scope", "get_engine"]
