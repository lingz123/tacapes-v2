"""Test DB fixture. Reuses the running tacapes-db Postgres container with
a dedicated `tacapes_test` database that is dropped + recreated per session.
TRUNCATEs all tables after every test to keep them independent."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tacapes.dashboard.db import init_engine
from tacapes.dashboard.db.models import Base

_TEST_DB_URL = "postgresql+psycopg://tacapes:tacapes@127.0.0.1:5433/tacapes_test"
_ADMIN_DB_URL = "postgresql+psycopg://tacapes:tacapes@127.0.0.1:5433/postgres"

_TABLES = ["positions", "missions", "price_quotes"]  # order matters: child first


def _recreate_test_db() -> None:
    admin = create_engine(_ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS tacapes_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE tacapes_test"))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_db() -> Iterator[None]:
    # Ensure the docker container is up; otherwise skip the dashboard tests
    # cleanly (lets unit tests for other packages run on hosts without Docker).
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "tacapes-db"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        pytest.skip("tacapes-db container is not running; skip dashboard tests")

    _recreate_test_db()
    os.environ["DATABASE_URL"] = _TEST_DB_URL
    init_engine(_TEST_DB_URL)

    engine = create_engine(_TEST_DB_URL)
    Base.metadata.create_all(engine)
    engine.dispose()
    yield


@pytest.fixture
def session() -> Iterator:
    """Yields a session whose data IS visible to route handlers (which open
    their own session_scope against the same DB). Tests commit through this
    session to make rows visible; the autouse `_clean` fixture wipes between tests."""
    from tacapes.dashboard.db import get_engine
    SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.rollback()
        sess.close()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    """TRUNCATE all dashboard tables after each test for isolation."""
    yield
    from tacapes.dashboard.db import get_engine
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE " + ", ".join(_TABLES) + " RESTART IDENTITY CASCADE"
        ))
