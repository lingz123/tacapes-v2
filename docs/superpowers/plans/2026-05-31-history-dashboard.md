# History Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mission-centric history dashboard backed by Postgres-in-Docker so every past tacapes run is browseable, with per-mission price-refreshed P&L, a New Mission form, and Delete/Failed-state handling. Spec: `docs/superpowers/specs/2026-05-31-history-dashboard-design.md`.

**Architecture:** Two processes (FastAPI host process + Postgres container) talking via `DATABASE_URL`. The existing `JobRunner` (single-worker ThreadPoolExecutor) runs the LangGraph pipeline in a worker thread and writes results to Postgres on completion. Pipeline output stage-JSON lives in JSONB columns; per-position data lives in a typed `positions` table; a `price_quotes` table is a 15-minute current-price cache.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX (vendored), SQLAlchemy 2.0 (sync), Alembic, psycopg3, Postgres 16 in Docker (bind mount), yfinance for prices.

**Scope guardrails:**
- The v2.1 fund/refresh-ticker/incremental-thesis code (`tacapes/fund.py`, `tacapes/refresh.py`, `tacapes/proposals.py`, `tacapes/schemas/fund.py`) stays on disk untouched. The dashboard does not import them.
- The existing `tacapes/dashboard/app.py`, `runners.py`, and fund-centric templates are **replaced**, not extended. `jobs.py` is **kept** as-is.
- Branch: `history-dashboard` (already created).

---

## File Structure

**New files:**
- `docker-compose.yml`. Postgres service with bind mount
- `alembic.ini`. Alembic config
- `scripts/check-db.sh`. `pg_isready` wrapper
- `tacapes/dashboard/db/__init__.py`. engine + `SessionLocal`
- `tacapes/dashboard/db/models.py`. SQLAlchemy models
- `tacapes/dashboard/db/repo.py`. query helpers
- `tacapes/dashboard/db/migrations/env.py`. Alembic env
- `tacapes/dashboard/db/migrations/script.py.mako`. Alembic template
- `tacapes/dashboard/db/migrations/versions/0001_initial.py`. initial schema
- `tacapes/dashboard/prices.py`. yfinance snapshot + cache
- `tacapes/dashboard/backfill.py`. portfolios/ → DB import
- `tacapes/dashboard/static/style.css`. color tokens for badges
- `tacapes/dashboard/templates/base.html`
- `tacapes/dashboard/templates/index.html` (rewrite)
- `tacapes/dashboard/templates/mission_new.html`
- `tacapes/dashboard/templates/mission_detail.html`
- `tacapes/dashboard/templates/_mission_row.html`
- `tacapes/dashboard/templates/_spinner.html`
- `tacapes/dashboard/templates/_failed.html`
- `tacapes/dashboard/templates/_done.html`
- `tests/dashboard/conftest.py`. test DB fixture, fake JobRunner
- `tests/dashboard/test_repo.py`
- `tests/dashboard/test_prices.py`
- `tests/dashboard/test_backfill.py`
- `tests/dashboard/test_routes.py`

**Modified files:**
- `pyproject.toml`. add deps
- `.env.example`. add `DATABASE_URL`
- `tacapes/cli.py:dashboard`. bootstrap DB + run backfill on first launch
- `tacapes/dashboard/app.py`. rewritten
- `tacapes/dashboard/runners.py`. rewritten

**Deleted files:**
- `tacapes/dashboard/templates/_book.html`
- `tacapes/dashboard/templates/_jobs.html`
- `tacapes/dashboard/templates/_memo.html`

---

## Phase 1: Storage Foundation

### Task 1.1: Add Python dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add runtime + dev deps to pyproject.toml**

Edit the `[project]` `dependencies` list to add (in alphabetical order):

```toml
"alembic>=1.13",
"psycopg[binary]>=3.2",
"sqlalchemy>=2.0",
"yfinance>=0.2.40",
```

Edit the `[project.optional-dependencies]` `dev` list to add:

```toml
"pytest-postgresql>=6.0",
```

(We use `pytest-postgresql` rather than `testcontainers` because it reuses the same Postgres container the dev already has running, no extra Docker layer.)

- [ ] **Step 2: Add DATABASE_URL to `.env.example`**

Append to `.env.example`:

```
# Postgres (matches docker-compose.yml service `db`)
DATABASE_URL=postgresql+psycopg://tacapes:tacapes@127.0.0.1:5433/tacapes
```

- [ ] **Step 3: Install dependencies**

Run: `cd /Users/mohamedalimanai/tacapes-v2 && source .venv/bin/activate && pip install -e .[dev]`
Expected: `Successfully installed alembic-... psycopg-... sqlalchemy-... yfinance-... pytest-postgresql-...`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "Add Postgres + Alembic + yfinance dependencies"
```

---

### Task 1.2: Docker Compose + pg_isready wrapper

**Files:**
- Create: `docker-compose.yml`
- Create: `scripts/check-db.sh`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: tacapes-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: tacapes
      POSTGRES_PASSWORD: tacapes
      POSTGRES_DB: tacapes
    volumes:
      - ~/.tacapes/pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tacapes -d tacapes"]
      interval: 5s
      timeout: 3s
      retries: 5
```

- [ ] **Step 2: Write `scripts/check-db.sh`**

```bash
#!/usr/bin/env bash
# Wait for the tacapes Postgres container to be ready.
set -euo pipefail
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5433}"
USER="${PGUSER:-tacapes}"
DB="${PGDATABASE:-tacapes}"
for i in {1..30}; do
  if docker exec tacapes-db pg_isready -U "$USER" -d "$DB" -h localhost >/dev/null 2>&1; then
    echo "db ready at ${HOST}:${PORT}/${DB}"
    exit 0
  fi
  sleep 1
done
echo "db did not become ready in 30s" >&2
exit 1
```

Then: `chmod +x scripts/check-db.sh`

- [ ] **Step 3: Start the container and verify**

Run: `cd /Users/mohamedalimanai/tacapes-v2 && docker compose up -d db && ./scripts/check-db.sh`
Expected: `db ready at 127.0.0.1:5433/tacapes`

- [ ] **Step 4: Verify bind mount persistence**

Run: `ls ~/.tacapes/pgdata | head -5`
Expected: Postgres data files (`base/`, `global/`, `pg_wal/`, etc.). confirms data lives in your home dir, not inside the container.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml scripts/check-db.sh
git commit -m "Add Postgres docker-compose service with bind mount"
```

---

### Task 1.3: SQLAlchemy models

**Files:**
- Create: `tacapes/dashboard/db/__init__.py`
- Create: `tacapes/dashboard/db/models.py`

- [ ] **Step 1: Write empty `db/__init__.py`**

```python
"""Postgres-backed persistence for the dashboard."""
```

(Engine + session factory lands in Task 1.5 once we have models to import.)

- [ ] **Step 2: Write `db/models.py` with SQLAlchemy 2.0 declarative**

```python
"""SQLAlchemy models for the dashboard's three tables (spec §4)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MissionStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    budget_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    max_positions: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_position_pct: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    horizon_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sectors_excluded: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    allow_shorts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[MissionStatus] = mapped_column(
        Enum(MissionStatus, name="mission_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    decomposition_json: Mapped[dict | None] = mapped_column(JSONB)
    assessments_json: Mapped[dict | None] = mapped_column(JSONB)
    shortlist_json: Mapped[dict | None] = mapped_column(JSONB)
    ta_outputs_json: Mapped[dict | None] = mapped_column(JSONB)
    memos_json: Mapped[dict | None] = mapped_column(JSONB)
    portfolio_json: Mapped[dict | None] = mapped_column(JSONB)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    positions: Mapped[list["Position"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_missions_status_created_at", "status", "created_at"),
        Index("ix_missions_created_at", "created_at"),
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    notional_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    entry_price_date: Mapped[datetime | None] = mapped_column(Date)

    mission: Mapped[Mission] = relationship(back_populates="positions")

    __table_args__ = (Index("ix_positions_ticker", "ticker"),)


class PriceQuote(Base):
    __tablename__ = "price_quotes"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 3: Smoke-import**

Run: `python -c "from tacapes.dashboard.db.models import Mission, Position, PriceQuote, MissionStatus; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add tacapes/dashboard/db/__init__.py tacapes/dashboard/db/models.py
git commit -m "Add SQLAlchemy models for missions, positions, price_quotes"
```

---

### Task 1.4: Alembic init + initial migration

**Files:**
- Create: `alembic.ini`
- Create: `tacapes/dashboard/db/migrations/env.py`
- Create: `tacapes/dashboard/db/migrations/script.py.mako`
- Create: `tacapes/dashboard/db/migrations/versions/0001_initial.py`

- [ ] **Step 1: Write `alembic.ini`**

```ini
[alembic]
script_location = tacapes/dashboard/db/migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write `migrations/env.py`**

```python
"""Alembic environment. Pulls URL from DATABASE_URL env var."""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from tacapes.dashboard.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
target_metadata = Base.metadata


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

- [ ] **Step 3: Write `migrations/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Generate the initial migration**

Run: `cd /Users/mohamedalimanai/tacapes-v2 && source .venv/bin/activate && set -a && source .env && set +a && alembic revision --autogenerate -m "initial: missions, positions, price_quotes" --rev-id 0001`
Expected: `Generating .../versions/0001_initial.py ... done`

- [ ] **Step 5: Inspect the generated migration**

Open `tacapes/dashboard/db/migrations/versions/0001_initial.py`. Verify it creates `mission_status` enum, `missions`, `positions`, `price_quotes`, plus the three indexes. If alembic missed the indexes, add them manually:

```python
op.create_index("ix_missions_status_created_at", "missions", ["status", "created_at"])
op.create_index("ix_missions_created_at", "missions", ["created_at"])
op.create_index("ix_positions_ticker", "positions", ["ticker"])
```

- [ ] **Step 6: Apply the migration and verify**

Run: `alembic upgrade head`
Expected: `Running upgrade -> 0001, initial: missions, positions, price_quotes`

Verify: `docker exec -it tacapes-db psql -U tacapes -d tacapes -c "\dt"`
Expected: 4 tables visible (`alembic_version`, `missions`, `positions`, `price_quotes`)

- [ ] **Step 7: Commit**

```bash
git add alembic.ini tacapes/dashboard/db/migrations
git commit -m "Add Alembic config and initial schema migration"
```

---

### Task 1.5: Engine + session factory + test fixture

**Files:**
- Modify: `tacapes/dashboard/db/__init__.py`
- Create: `tests/dashboard/__init__.py`
- Create: `tests/dashboard/conftest.py`

- [ ] **Step 1: Write `db/__init__.py` with engine + sessionmaker**

```python
"""Postgres-backed persistence for the dashboard."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _engine_for(url: str | None = None):
    return create_engine(
        url or os.environ["DATABASE_URL"], pool_pre_ping=True, future=True
    )


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> None:
    """Configure the module-level engine + session factory. Idempotent."""
    global _engine, _SessionLocal
    _engine = _engine_for(url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


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


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


__all__ = ["init_engine", "session_scope", "get_engine"]
```

- [ ] **Step 2: Write `tests/dashboard/__init__.py`**

```python
```

(Empty file, makes the directory a package.)

- [ ] **Step 3: Write `tests/dashboard/conftest.py`**

The fixture uses TRUNCATE-after-test for isolation (instead of nested-transaction rollback), because route-handler tests call `session_scope()` in the production code which opens its own DB session. Nested-transaction tricks don't reach those sessions; a clean TRUNCATE between tests does.

```python
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
        conn.execute(text("DROP DATABASE IF EXISTS tacapes_test"))
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
    SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
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
```

- [ ] **Step 4: Run an empty test to verify the fixture wires up**

Run: `pytest tests/dashboard/ -v`
Expected: `no tests ran in ...s` (no tests yet, no errors)

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/db/__init__.py tests/dashboard/__init__.py tests/dashboard/conftest.py
git commit -m "Add DB engine/session helpers and test DB fixture"
```

---

### Task 1.6: Repo helpers

**Files:**
- Create: `tacapes/dashboard/db/repo.py`
- Create: `tests/dashboard/test_repo.py`

- [ ] **Step 1: Write the failing test**

`tests/dashboard/test_repo.py`:

```python
"""Repo function tests. Each function in repo.py gets at least one test."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from tacapes.dashboard.db import repo
from tacapes.dashboard.db.models import Mission, MissionStatus, Position


def _new_mission_kwargs() -> dict:
    return {
        "statement": "Buy nuclear power names benefiting from AI/data center demand " * 2,
        "budget_usd": Decimal("20000.00"),
        "max_positions": 4,
        "max_position_pct": Decimal("0.400"),
        "horizon_months": 24,
        "sectors_excluded": [],
        "allow_shorts": False,
    }


def test_insert_mission_returns_queued_row(session):
    row = repo.insert_mission(session, **_new_mission_kwargs())
    session.flush()
    assert isinstance(row.id, UUID)
    assert row.status == MissionStatus.queued
    assert row.started_at is None
    assert row.completed_at is None


def test_mark_running_then_done_updates_timestamps_and_jsonb(session):
    row = repo.insert_mission(session, **_new_mission_kwargs())
    session.flush()

    repo.mark_running(session, row.id)
    session.flush()
    refreshed = session.get(Mission, row.id)
    assert refreshed.status == MissionStatus.running
    assert refreshed.started_at is not None

    repo.mark_done(
        session,
        row.id,
        decomposition_json={"sub_themes": []},
        assessments_json={},
        shortlist_json={"candidates": []},
        ta_outputs_json={},
        memos_json={},
        portfolio_json={"positions": [], "cash_reserve_pct": 1.0},
        cost_usd=Decimal("1.23"),
    )
    session.flush()
    refreshed = session.get(Mission, row.id)
    assert refreshed.status == MissionStatus.done
    assert refreshed.completed_at is not None
    assert refreshed.portfolio_json == {"positions": [], "cash_reserve_pct": 1.0}
    assert refreshed.cost_usd == Decimal("1.23")


def test_mark_failed_writes_short_error_message(session):
    row = repo.insert_mission(session, **_new_mission_kwargs())
    session.flush()

    repo.mark_failed(session, row.id, "x" * 500)
    session.flush()
    refreshed = session.get(Mission, row.id)
    assert refreshed.status == MissionStatus.failed
    assert refreshed.error_message is not None
    assert len(refreshed.error_message) <= 200


def test_insert_positions_and_cascade_delete(session):
    row = repo.insert_mission(session, **_new_mission_kwargs())
    session.flush()
    repo.insert_positions(
        session,
        row.id,
        [
            {
                "ticker": "NRG",
                "weight_pct": Decimal("0.2500"),
                "notional_usd": Decimal("5000.00"),
                "rationale": "test",
                "entry_price": Decimal("100.00"),
                "entry_price_date": datetime(2026, 5, 31, tzinfo=UTC).date(),
            },
        ],
    )
    session.flush()
    assert session.query(Position).filter_by(mission_id=row.id).count() == 1

    repo.delete_mission(session, row.id)
    session.flush()
    assert session.query(Position).filter_by(mission_id=row.id).count() == 0
    assert session.get(Mission, row.id) is None


def test_list_missions_orders_newest_first(session):
    a = repo.insert_mission(session, **_new_mission_kwargs())
    b = repo.insert_mission(session, **_new_mission_kwargs())
    session.flush()

    rows = repo.list_missions(session)
    ids = [r.id for r in rows]
    # b inserted after a → b appears first
    assert ids.index(b.id) < ids.index(a.id)


def test_get_mission_with_positions(session):
    row = repo.insert_mission(session, **_new_mission_kwargs())
    session.flush()
    repo.insert_positions(
        session,
        row.id,
        [{"ticker": "NRG", "weight_pct": Decimal("0.5"),
          "notional_usd": Decimal("10000"), "rationale": None,
          "entry_price": None, "entry_price_date": None}],
    )
    session.flush()
    fetched = repo.get_mission_with_positions(session, row.id)
    assert fetched is not None
    assert len(fetched.positions) == 1
    assert fetched.positions[0].ticker == "NRG"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/dashboard/test_repo.py -v`
Expected: ImportError on `tacapes.dashboard.db.repo` (module does not exist yet).

- [ ] **Step 3: Implement `db/repo.py`**

```python
"""Thin query helpers over the SQLAlchemy models. Each function takes a
Session and does ONE focused unit of work. All datetimes are timezone-aware UTC."""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Mission, MissionStatus, Position


def insert_mission(
    session: Session,
    *,
    statement: str,
    budget_usd: Decimal,
    max_positions: int,
    max_position_pct: Decimal,
    horizon_months: int,
    sectors_excluded: list[str],
    allow_shorts: bool,
) -> Mission:
    row = Mission(
        statement=statement,
        budget_usd=budget_usd,
        max_positions=max_positions,
        max_position_pct=max_position_pct,
        horizon_months=horizon_months,
        sectors_excluded=sectors_excluded,
        allow_shorts=allow_shorts,
        status=MissionStatus.queued,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    return row


def mark_running(session: Session, mission_id: uuid.UUID) -> None:
    row = session.get(Mission, mission_id)
    if row is None:
        raise LookupError(f"mission {mission_id} not found")
    row.status = MissionStatus.running
    row.started_at = datetime.now(UTC)


def mark_done(
    session: Session,
    mission_id: uuid.UUID,
    *,
    decomposition_json: dict | None,
    assessments_json: dict | None,
    shortlist_json: dict | None,
    ta_outputs_json: dict | None,
    memos_json: dict | None,
    portfolio_json: dict | None,
    cost_usd: Decimal | None,
) -> None:
    row = session.get(Mission, mission_id)
    if row is None:
        raise LookupError(f"mission {mission_id} not found")
    row.status = MissionStatus.done
    row.completed_at = datetime.now(UTC)
    row.decomposition_json = decomposition_json
    row.assessments_json = assessments_json
    row.shortlist_json = shortlist_json
    row.ta_outputs_json = ta_outputs_json
    row.memos_json = memos_json
    row.portfolio_json = portfolio_json
    row.cost_usd = cost_usd


def mark_failed(
    session: Session, mission_id: uuid.UUID, error_message: str
) -> None:
    row = session.get(Mission, mission_id)
    if row is None:
        raise LookupError(f"mission {mission_id} not found")
    row.status = MissionStatus.failed
    row.completed_at = datetime.now(UTC)
    row.error_message = error_message[:200]


def insert_positions(
    session: Session,
    mission_id: uuid.UUID,
    rows: Iterable[dict[str, Any]],
) -> None:
    session.add_all(
        Position(mission_id=mission_id, **r) for r in rows
    )


def list_missions(session: Session) -> list[Mission]:
    stmt = select(Mission).order_by(Mission.created_at.desc())
    return list(session.scalars(stmt))


def get_mission_with_positions(
    session: Session, mission_id: uuid.UUID
) -> Mission | None:
    stmt = (
        select(Mission)
        .options(selectinload(Mission.positions))
        .where(Mission.id == mission_id)
    )
    return session.scalars(stmt).one_or_none()


def delete_mission(session: Session, mission_id: uuid.UUID) -> bool:
    row = session.get(Mission, mission_id)
    if row is None:
        return False
    session.delete(row)
    return True


def reset_orphaned_running(session: Session) -> int:
    """Mark any rows still in 'running' as failed. Called at startup to clean
    up after a host-process crash."""
    rows = list(session.scalars(select(Mission).where(Mission.status == MissionStatus.running)))
    for row in rows:
        row.status = MissionStatus.failed
        row.completed_at = datetime.now(UTC)
        row.error_message = "process restart"
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/dashboard/test_repo.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/db/repo.py tests/dashboard/test_repo.py
git commit -m "Add repo query helpers and tests"
```

---

### Task 1.7: Bootstrap DB in `tacapes dashboard`

**Files:**
- Modify: `tacapes/cli.py` (the `dashboard` command function)

- [ ] **Step 1: Read the current dashboard command**

The current `dashboard` command lives around `tacapes/cli.py:433-450`. It imports `create_app` and launches uvicorn. We need to insert a DB bootstrap before uvicorn starts: confirm reachable, run `alembic upgrade head`, reset orphaned `running` rows, then trigger backfill (backfill itself comes in Phase 2; for this task we just hook the bootstrap).

- [ ] **Step 2: Add a `bootstrap_db` helper in `tacapes/dashboard/__init__.py`**

Find the existing `tacapes/dashboard/__init__.py` (it has 77 bytes, just an exports stub). Add a bootstrap function:

```python
"""Dashboard package: FastAPI app, JobRunner, DB."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def bootstrap_db() -> None:
    """Verify DATABASE_URL, run alembic, reset orphaned rows. Call at dashboard start."""
    if "DATABASE_URL" not in os.environ:
        print(
            "ERROR: DATABASE_URL not set. Did you copy .env.example to .env "
            "and run `docker compose up -d db`?",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # Run alembic upgrade head from the project root.
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if result.returncode != 0:
        print(f"alembic upgrade head failed:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(2)
    log.info("alembic: %s", result.stderr.strip().splitlines()[-1] if result.stderr else "ok")

    # Reset orphaned 'running' rows from a previous crashed run.
    from .db import session_scope
    from .db.repo import reset_orphaned_running

    with session_scope() as session:
        reset = reset_orphaned_running(session)
        if reset:
            log.info("startup recovery: reset %d orphaned running mission(s)", reset)
```

- [ ] **Step 3: Modify the `dashboard` CLI command to call `bootstrap_db`**

In `tacapes/cli.py`, find the `dashboard` function (≈ line 433) and insert the bootstrap call before `create_app`:

```python
@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8732, "--port", help="Bind port"),
) -> None:
    """Launch the local web dashboard (FastAPI + HTMX on 127.0.0.1:8732)."""
    import uvicorn  # noqa: PLC0415

    from .dashboard import bootstrap_db  # noqa: PLC0415
    from .dashboard.app import create_app  # noqa: PLC0415

    bootstrap_db()

    _CONSOLE.print(
        f"  [ok]dashboard[/]  ·  [bold]http://{host}:{port}[/]  "
        # ... (preserve the rest of the existing message verbatim)
    )
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
```

- [ ] **Step 4: Manual smoke test**

Run: `cd /Users/mohamedalimanai/tacapes-v2 && source .venv/bin/activate && set -a && source .env && set +a && tacapes dashboard --port 8732`
Expected:
- Logs "alembic: ..." and (if applicable) "startup recovery: reset N..."
- uvicorn starts on 127.0.0.1:8732 without error.
- `curl http://127.0.0.1:8732/` still renders the *old* fund-centric page (we rewrite app.py in Phase 3). The point of this test is the bootstrap path, not the page.

Press Ctrl-C to stop.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/__init__.py tacapes/cli.py
git commit -m "Bootstrap Postgres + migrations + orphan recovery on dashboard launch"
```

---

## Phase 2: Backfill Existing Mission Folders

### Task 2.1: Price snapshot module (today's close + historical lookup)

**Files:**
- Create: `tacapes/dashboard/prices.py`
- Create: `tests/dashboard/test_prices.py`

- [ ] **Step 1: Write the failing tests**

`tests/dashboard/test_prices.py`:

```python
"""yfinance is stubbed; we never hit the network in tests."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tacapes.dashboard import prices


def _fake_history(closes: dict[str, float]):
    """Build a `yf.Ticker` stub whose .history() returns a DataFrame with the
    given close prices keyed by ticker (caller picks one)."""
    def factory(ticker: str):
        mock = MagicMock()
        if ticker in closes:
            mock.history.return_value = pd.DataFrame(
                {"Close": [closes[ticker]]},
                index=pd.DatetimeIndex([pd.Timestamp("2026-05-30")], tz="UTC"),
            )
        else:
            mock.history.return_value = pd.DataFrame()
        return mock
    return factory


def test_snapshot_entry_price_for_today_returns_close():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 95.42})):
        price, date_used = prices.snapshot_entry_price("NRG")
    assert price == Decimal("95.42")
    assert isinstance(date_used, date)


def test_snapshot_entry_price_returns_none_on_yfinance_miss():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({})):
        price, date_used = prices.snapshot_entry_price("XXXX")
    assert price is None
    assert date_used is None


def test_historical_entry_price_finds_close_within_week():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 80.0})):
        price, date_used = prices.historical_entry_price(
            "NRG", on_date=date(2026, 5, 30)
        )
    assert price == Decimal("80.00")


def test_historical_entry_price_none_on_miss():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({})):
        price, date_used = prices.historical_entry_price(
            "XXXX", on_date=date(2026, 5, 30)
        )
    assert price is None
    assert date_used is None
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/dashboard/test_prices.py -v`
Expected: `ModuleNotFoundError: tacapes.dashboard.prices`.

- [ ] **Step 3: Implement `prices.py`** (snapshot + historical lookup; cache helpers come in Task 3.1)

```python
"""yfinance-backed price helpers. Two functions for entry-price snapshots:
- `snapshot_entry_price(ticker)` for missions completing now.
- `historical_entry_price(ticker, on_date)` for backfilling old missions.

Both return (price, date_used) or (None, None) on miss. Never raise on
yfinance failure. the caller persists NULL."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf  # type: ignore[import-untyped]

log = logging.getLogger(__name__)


def _first_close(df) -> Decimal | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    try:
        value = float(df["Close"].iloc[0])
    except (IndexError, ValueError):
        return None
    return Decimal(f"{value:.4f}").normalize().quantize(Decimal("0.01"))


def snapshot_entry_price(ticker: str) -> tuple[Decimal | None, date | None]:
    """Most recent close for `ticker`. NULL on miss."""
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="5d")  # last 5 trading days
    except Exception as e:
        log.warning("yfinance snapshot failed for %s: %s", ticker, e)
        return None, None
    if df is None or df.empty:
        return None, None
    price = _first_close(df.tail(1))
    if price is None:
        return None, None
    date_used = df.index[-1].date()
    return price, date_used


def historical_entry_price(
    ticker: str, on_date: date
) -> tuple[Decimal | None, date | None]:
    """Close on `on_date`, or the first trading day in the following 7 days
    if `on_date` was a weekend/holiday. NULL on miss."""
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(
            start=on_date.isoformat(),
            end=(on_date + timedelta(days=7)).isoformat(),
        )
    except Exception as e:
        log.warning("yfinance historical failed for %s @ %s: %s", ticker, on_date, e)
        return None, None
    if df is None or df.empty:
        return None, None
    price = _first_close(df.head(1))
    if price is None:
        return None, None
    date_used = df.index[0].date()
    return price, date_used
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/dashboard/test_prices.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/prices.py tests/dashboard/test_prices.py
git commit -m "Add yfinance entry-price helpers (snapshot + historical lookup)"
```

---

### Task 2.2: Backfill module + test

**Files:**
- Create: `tacapes/dashboard/backfill.py`
- Create: `tests/dashboard/test_backfill.py`
- Create: `tests/dashboard/fixtures/portfolios/<uuid>/...` (fixture data, see step 1)

- [ ] **Step 1: Create a fixture portfolio folder**

Build a minimal but complete fixture under `tests/dashboard/fixtures/portfolios/00000000-0000-0000-0000-000000000001/`. Use the same layout as a real `~/.tacapes/portfolios/<id>/` folder. Minimum files for the backfill to consume:

- `mission.json`:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "statement": "Test mission statement that is long enough to satisfy validators please.",
  "budget_usd": 20000,
  "constraints": {
    "max_position_pct": 0.4,
    "max_positions": 4,
    "sectors_excluded": [],
    "allow_shorts": false,
    "time_horizon_months": 12
  },
  "created_at": "2026-04-01T12:00:00+00:00"
}
```

- `decomposition.json`: `{"mission_id":"...","sub_themes":[]}`
- `shortlist.json`: `{"mission_id":"...","candidates":[]}`
- `portfolio.json`:

```json
{
  "mission_id": "00000000-0000-0000-0000-000000000001",
  "mode": "cold_start",
  "total_budget_usd": 20000,
  "positions": [
    {"ticker":"NRG","weight_pct":0.5,"notional_usd":10000,"rationale":"test","is_short":false},
    {"ticker":"CEG","weight_pct":0.4,"notional_usd":8000,"rationale":"test","is_short":false}
  ],
  "correlation_map": [],
  "cash_reserve_pct": 0.1,
  "rationale": "test"
}
```

- `assessments/` (empty directory), `ta_outputs/` (empty), `memos/` (empty).

Also create a *broken* fixture: `tests/dashboard/fixtures/portfolios/broken/` with a `mission.json` that's just `not json`. Backfill should skip it.

- [ ] **Step 2: Write the failing tests**

`tests/dashboard/test_backfill.py`:

```python
"""Backfill test: convert an on-disk portfolios/ folder tree into DB rows."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tacapes.dashboard import backfill, prices
from tacapes.dashboard.db.models import Mission, MissionStatus, Position

_FIXTURES = Path(__file__).parent / "fixtures" / "portfolios"


def _fake_historical(ticker, on_date):
    from decimal import Decimal
    from datetime import date
    return Decimal("100.00"), date(2026, 4, 1)


def test_backfill_imports_one_good_mission_skips_broken(session):
    with patch.object(prices, "historical_entry_price", side_effect=_fake_historical):
        n = backfill.backfill_from_disk(session, _FIXTURES)

    assert n == 1
    rows = session.query(Mission).all()
    assert len(rows) == 1
    assert rows[0].status == MissionStatus.done
    assert rows[0].portfolio_json["positions"][0]["ticker"] == "NRG"

    positions = session.query(Position).all()
    assert {p.ticker for p in positions} == {"NRG", "CEG"}
    for p in positions:
        assert p.entry_price is not None
        assert p.entry_price_date is not None


def test_backfill_is_no_op_on_already_present_mission(session):
    with patch.object(prices, "historical_entry_price", side_effect=_fake_historical):
        backfill.backfill_from_disk(session, _FIXTURES)
        n_second = backfill.backfill_from_disk(session, _FIXTURES)
    assert n_second == 0  # idempotent
```

- [ ] **Step 3: Run tests, verify failure**

Run: `pytest tests/dashboard/test_backfill.py -v`
Expected: `ModuleNotFoundError: tacapes.dashboard.backfill`.

- [ ] **Step 4: Implement `backfill.py`**

```python
"""One-shot importer: ~/.tacapes/portfolios/<uuid>/  →  Postgres rows.

Called on dashboard startup IFF the missions table is empty. Idempotent:
already-imported mission ids are skipped."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from . import prices
from .db.models import Mission, MissionStatus, Position

log = logging.getLogger(__name__)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.warning("could not parse %s: %s", path, e)
        return None


def _merge_dir(directory: Path, key_field: str | None = None) -> dict:
    """Read every *.json in directory into a single dict. If `key_field` is
    given, use that field from each file's payload as the dict key; otherwise
    use the filename stem (e.g. ticker, sub_theme_id)."""
    out: dict = {}
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            continue
        key = payload.get(key_field) if key_field else path.stem
        out[str(key)] = payload
    return out


def backfill_one_folder(session: Session, folder: Path) -> bool:
    """Backfill a single mission folder. Returns True if a row was inserted."""
    mission_payload = _read_json(folder / "mission.json")
    if mission_payload is None:
        log.warning("skip %s: no parseable mission.json", folder.name)
        return False

    try:
        mission_id = uuid.UUID(mission_payload["id"])
    except (KeyError, ValueError):
        log.warning("skip %s: invalid mission id", folder.name)
        return False

    if session.get(Mission, mission_id) is not None:
        return False  # already imported

    constraints = mission_payload.get("constraints", {})
    portfolio = _read_json(folder / "portfolio.json") or {}
    created_at = datetime.fromisoformat(mission_payload["created_at"])

    row = Mission(
        id=mission_id,
        statement=mission_payload["statement"],
        budget_usd=Decimal(str(mission_payload["budget_usd"])),
        max_positions=int(constraints.get("max_positions", 5)),
        max_position_pct=Decimal(str(constraints.get("max_position_pct", 0.4))),
        horizon_months=int(constraints.get("time_horizon_months", 12)),
        sectors_excluded=list(constraints.get("sectors_excluded", [])),
        allow_shorts=bool(constraints.get("allow_shorts", False)),
        status=MissionStatus.done,
        created_at=created_at,
        started_at=created_at,
        completed_at=created_at,
        decomposition_json=_read_json(folder / "decomposition.json"),
        assessments_json=_merge_dir(folder / "assessments"),
        shortlist_json=_read_json(folder / "shortlist.json"),
        ta_outputs_json=_merge_dir(folder / "ta_outputs"),
        memos_json=_merge_dir(folder / "memos"),
        portfolio_json=portfolio or None,
        cost_usd=None,
    )
    session.add(row)

    for p in portfolio.get("positions", []):
        ticker = p["ticker"]
        entry_price, entry_date = prices.historical_entry_price(
            ticker, on_date=created_at.date()
        )
        session.add(
            Position(
                mission_id=mission_id,
                ticker=ticker,
                weight_pct=Decimal(str(p["weight_pct"])),
                notional_usd=Decimal(str(p["notional_usd"])),
                rationale=p.get("rationale"),
                entry_price=entry_price,
                entry_price_date=entry_date,
            )
        )

    return True


def backfill_from_disk(session: Session, portfolios_root: Path) -> int:
    """Import every well-formed mission folder under `portfolios_root`.
    Returns count of newly-inserted mission rows."""
    if not portfolios_root.exists():
        return 0
    inserted = 0
    for child in sorted(portfolios_root.iterdir()):
        if not child.is_dir():
            continue
        try:
            if backfill_one_folder(session, child):
                inserted += 1
        except Exception as e:  # noqa: BLE001. a bad folder must not kill the import
            log.warning("skip %s: %s", child.name, e)
    return inserted
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/dashboard/test_backfill.py -v`
Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add tacapes/dashboard/backfill.py tests/dashboard/test_backfill.py tests/dashboard/fixtures
git commit -m "Add portfolios/ → DB backfill with idempotent skip"
```

---

### Task 2.3: Trigger backfill on first dashboard launch

**Files:**
- Modify: `tacapes/dashboard/__init__.py` (the `bootstrap_db` function added in Task 1.7)

- [ ] **Step 1: Extend `bootstrap_db` to run backfill when missions is empty**

Edit `tacapes/dashboard/__init__.py`. After the orphan-recovery block in `bootstrap_db`, add:

```python
    # First-launch backfill of existing ~/.tacapes/portfolios/.
    from .backfill import backfill_from_disk
    from .db.repo import list_missions
    from ..config import tacapes_home

    with session_scope() as session:
        if not list_missions(session):
            portfolios = tacapes_home() / "portfolios"
            log.info("missions table empty. backfilling from %s", portfolios)
            n = backfill_from_disk(session, portfolios)
            log.info("backfill: inserted %d mission(s)", n)
```

(The `session_scope` import you already added in Task 1.7 is reused.)

- [ ] **Step 2: Manual smoke test against the real home dir**

This will hit yfinance for historical prices. it's slow (1 call per position × 20 missions). If you want to skip yfinance for the smoke test, temporarily monkey-patch `historical_entry_price` to return `(None, None)`.

Run: `tacapes dashboard --port 8732`
Expected log lines (the first time only):
- `alembic: ...`
- `missions table empty. backfilling from /Users/.../.tacapes/portfolios`
- `backfill: inserted 20 mission(s)` (or whatever your count is)

Then Ctrl-C and verify:
```
docker exec tacapes-db psql -U tacapes -d tacapes -c "SELECT COUNT(*) FROM missions; SELECT COUNT(*) FROM positions WHERE entry_price IS NOT NULL;"
```

- [ ] **Step 3: Run dashboard a second time, verify no re-import**

Run: `tacapes dashboard --port 8732`
Expected: no "backfilling from" log line. `missions` count is unchanged.

- [ ] **Step 4: Commit**

```bash
git add tacapes/dashboard/__init__.py
git commit -m "Run backfill on first launch when missions table is empty"
```

---

## Phase 3: Read-Only History UI

### Task 3.1: Current-price cache + refresh in `prices.py`

**Files:**
- Modify: `tacapes/dashboard/prices.py`
- Modify: `tests/dashboard/test_prices.py`

- [ ] **Step 1: Add failing tests for current-price cache**

Append to `tests/dashboard/test_prices.py`:

```python
from datetime import timedelta

from sqlalchemy import select

from tacapes.dashboard.db.models import PriceQuote


def test_get_current_prices_inserts_missing_quotes(session):
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 90.0, "CEG": 50.0})):
        out = prices.get_current_prices(session, ["NRG", "CEG"])
    assert out["NRG"] == Decimal("90.00")
    assert out["CEG"] == Decimal("50.00")
    saved = {q.ticker for q in session.scalars(select(PriceQuote))}
    assert saved == {"NRG", "CEG"}


def test_get_current_prices_returns_cached_within_window(session):
    # Pre-seed a fresh quote
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("123.00"),
        fetched_at=datetime.now(UTC) - timedelta(minutes=5),
    ))
    session.flush()
    # The fake yfinance returns a different value; cached one should win.
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 999.0})):
        out = prices.get_current_prices(session, ["NRG"])
    assert out["NRG"] == Decimal("123.00")


def test_get_current_prices_refreshes_stale_quotes(session):
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("123.00"),
        fetched_at=datetime.now(UTC) - timedelta(hours=2),
    ))
    session.flush()
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 200.0})):
        out = prices.get_current_prices(session, ["NRG"])
    assert out["NRG"] == Decimal("200.00")


def test_invalidate_price_cache(session):
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("1.0"),
        fetched_at=datetime.now(UTC),
    ))
    session.flush()
    prices.invalidate_price_cache(session)
    session.flush()
    quote = session.get(PriceQuote, "NRG")
    assert quote is None or quote.fetched_at.year < 2020
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/dashboard/test_prices.py -v`
Expected: AttributeError / ImportError on `get_current_prices` and `invalidate_price_cache`.

- [ ] **Step 3: Implement cache functions in `prices.py`**

Append to `tacapes/dashboard/prices.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db.models import PriceQuote

CACHE_TTL = timedelta(minutes=15)


def get_current_prices(
    session: Session, tickers: list[str]
) -> dict[str, Decimal | None]:
    """Return {ticker: current_price_or_None}. Fetches and upserts any missing
    or stale quotes. yfinance failures result in None for that ticker."""
    if not tickers:
        return {}
    cutoff = datetime.now(UTC) - CACHE_TTL
    rows = list(session.scalars(
        select(PriceQuote).where(PriceQuote.ticker.in_(tickers))
    ))
    fresh: dict[str, Decimal] = {
        r.ticker: r.price for r in rows if r.fetched_at >= cutoff
    }
    stale_or_missing = [t for t in tickers if t not in fresh]

    for ticker in stale_or_missing:
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="5d")
        except Exception as e:
            log.warning("current price fetch failed for %s: %s", ticker, e)
            continue
        price = _first_close(df.tail(1) if df is not None and not df.empty else None)
        if price is None:
            continue
        existing = session.get(PriceQuote, ticker)
        if existing is None:
            session.add(PriceQuote(
                ticker=ticker, price=price, fetched_at=datetime.now(UTC),
            ))
        else:
            existing.price = price
            existing.fetched_at = datetime.now(UTC)
        fresh[ticker] = price

    return {t: fresh.get(t) for t in tickers}


def invalidate_price_cache(session: Session) -> None:
    """Force the next get_current_prices to re-fetch every ticker."""
    session.execute(delete(PriceQuote))
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/dashboard/test_prices.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/prices.py tests/dashboard/test_prices.py
git commit -m "Add 15-min price cache and invalidation"
```

---

### Task 3.2: Replace `app.py` with the new mission-centric shell

**Files:**
- Modify: `tacapes/dashboard/app.py` (full rewrite)
- Delete: `tacapes/dashboard/templates/_book.html`, `_jobs.html`, `_memo.html`, `index.html` (the old one; we write the new index.html in Task 3.4)

- [ ] **Step 1: Delete the fund-centric templates**

```bash
cd /Users/mohamedalimanai/tacapes-v2
rm tacapes/dashboard/templates/_book.html
rm tacapes/dashboard/templates/_jobs.html
rm tacapes/dashboard/templates/_memo.html
rm tacapes/dashboard/templates/index.html
```

- [ ] **Step 2: Rewrite `tacapes/dashboard/app.py` as a minimal shell**

The full route set lands across Tasks 3.4, 3.5, 3.6, 4.2-4.4, 5.4. For now we just need `create_app`, `/healthz`, and templating set up.

```python
"""FastAPI app for the tacapes history dashboard.

Routes:
  GET  /                       history page
  GET  /healthz                DB ping
  GET  /missions/new           new-mission form              (Task 4.2)
  POST /missions               enqueue a mission             (Task 4.3)
  GET  /missions/{id}          detail page                   (Task 3.5)
  GET  /missions/{id}/status   HTMX poll fragment            (Task 4.4)
  POST /missions/{id}/delete   delete a mission              (Task 5.4)
  POST /prices/refresh         invalidate the 15-min cache   (Task 3.6)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_DIR = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_DIR / "templates"))


def create_app(*, job_runner: Any | None = None) -> FastAPI:
    """Build the dashboard app. Pass `job_runner` to inject a fake in tests."""
    from .jobs import JobRunner

    app = FastAPI(title="tacapes history dashboard")
    app.state.job_runner = job_runner if job_runner is not None else JobRunner()
    app.state.templates = _TEMPLATES
    app.mount(
        "/static", StaticFiles(directory=str(_DIR / "static")), name="static"
    )

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        from sqlalchemy import text
        from .db import get_engine
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse({"ok": True})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=503)

    # Routes registered here in later tasks (3.4, 3.5, 3.6, 4.2-4.4, 5.4).
    from . import routes
    routes.register(app)

    return app
```

- [ ] **Step 3: Create the empty `routes.py` module so the import works**

`tacapes/dashboard/routes.py`:

```python
"""Route handlers, split out so each phase can append cleanly."""
from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    """Hooked from create_app(). Each task appends its routes here."""
    pass
```

- [ ] **Step 4: Smoke test that the app at least starts**

Run: `cd /Users/mohamedalimanai/tacapes-v2 && tacapes dashboard --port 8732`
Expected: no errors. `curl http://127.0.0.1:8732/healthz` returns `{"ok":true}`.

Ctrl-C to stop.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/app.py tacapes/dashboard/routes.py
git rm tacapes/dashboard/templates/_book.html tacapes/dashboard/templates/_jobs.html tacapes/dashboard/templates/_memo.html tacapes/dashboard/templates/index.html
git commit -m "Rewrite dashboard app shell, drop fund-centric templates"
```

---

### Task 3.3: Base template + style.css

**Files:**
- Create: `tacapes/dashboard/templates/base.html`
- Create: `tacapes/dashboard/static/style.css`

- [ ] **Step 1: Write `base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}tacapes{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', path='style.css') }}">
  <script src="{{ url_for('static', path='htmx.min.js') }}"></script>
</head>
<body>
  <header class="topbar">
    <a href="/" class="brand">tacapes</a>
    <nav>
      <a href="/missions/new" class="btn btn-primary">+ new mission</a>
      <form method="post" action="/prices/refresh" style="display:inline">
        <button type="submit" class="btn">refresh prices</button>
      </form>
    </nav>
  </header>
  <main>
    {% block body %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 2: Write `style.css`**

```css
:root {
  --fg: #111;
  --muted: #777;
  --bg: #fafafa;
  --line: #e4e4e4;
  --queued: #b08800;
  --running: #2e6df1;
  --done: #1e7e34;
  --failed: #c93838;
  --pnl-up: #1e7e34;
  --pnl-down: #c93838;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.4 -apple-system, sans-serif; color: var(--fg); background: var(--bg); }
.topbar { display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; border-bottom: 1px solid var(--line); background: white; }
.brand { font-weight: 600; font-size: 16px; text-decoration: none; color: var(--fg); }
main { padding: 24px; max-width: 1100px; margin: 0 auto; }
.btn { display: inline-block; padding: 6px 12px; border: 1px solid var(--line);
  border-radius: 4px; background: white; cursor: pointer; text-decoration: none;
  color: var(--fg); font-size: 13px; }
.btn:hover { background: var(--bg); }
.btn-primary { background: var(--fg); color: white; border-color: var(--fg); }
.btn-danger { color: var(--failed); }
table.history { width: 100%; border-collapse: collapse; }
table.history th, table.history td { padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; }
table.history th { font-size: 12px; text-transform: uppercase; color: var(--muted); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.badge.queued { background: #fff7e0; color: var(--queued); }
.badge.running { background: #e8f0ff; color: var(--running); }
.badge.done { background: #e8f5ec; color: var(--done); }
.badge.failed { background: #fbe8e8; color: var(--failed); }
.pnl.up { color: var(--pnl-up); }
.pnl.down { color: var(--pnl-down); }
.spinner { display: inline-block; width: 18px; height: 18px;
  border: 2px solid var(--line); border-top-color: var(--running);
  border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }
.statement-preview { color: var(--fg); max-width: 540px; }
.muted { color: var(--muted); font-size: 12px; }
section { margin-bottom: 32px; }
section h2 { font-size: 14px; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--line); padding-bottom: 6px; }
details.report { margin: 6px 0; }
details.report summary { cursor: pointer; padding: 6px 0; }
.failed-panel { padding: 32px; text-align: center; color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; }
```

- [ ] **Step 3: Smoke test in browser**

Run: `tacapes dashboard --port 8732` and visit `http://127.0.0.1:8732/healthz`.
(We don't have `/` yet; that's Task 3.4. This just confirms templates and static files are reachable.)

- [ ] **Step 4: Commit**

```bash
git add tacapes/dashboard/templates/base.html tacapes/dashboard/static/style.css
git commit -m "Add base template and style.css"
```

---

### Task 3.4: History page (`GET /`)

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Create: `tacapes/dashboard/templates/index.html`
- Create: `tacapes/dashboard/templates/_mission_row.html`
- Create: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

`tests/dashboard/test_routes.py`:

```python
"""Route tests using FastAPI TestClient against the real test DB."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tacapes.dashboard.app import create_app
from tacapes.dashboard.db import session_scope
from tacapes.dashboard.db.models import (
    Mission, MissionStatus, Position, PriceQuote,
)
from tacapes.dashboard import prices


class _SyncJobRunner:
    """Runs `fn` immediately on submit; mirrors JobRunner's submit signature."""
    def submit(self, *, kind, target, fn):
        fn(lambda msg: None)
    def list_jobs(self):
        return []
    def drain_completed(self):
        return set()


@pytest.fixture
def client():
    return TestClient(create_app(job_runner=_SyncJobRunner()))


def _insert_done_mission(session, *, statement, positions):
    row = Mission(
        statement=statement,
        budget_usd=Decimal("20000"),
        max_positions=4,
        max_position_pct=Decimal("0.4"),
        horizon_months=12,
        sectors_excluded=[],
        allow_shorts=False,
        status=MissionStatus.done,
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        portfolio_json={"positions": positions, "cash_reserve_pct": 0.0, "rationale": "t"},
        cost_usd=Decimal("12.50"),
    )
    session.add(row)
    session.flush()
    for p in positions:
        session.add(Position(
            mission_id=row.id, ticker=p["ticker"],
            weight_pct=Decimal(str(p["weight_pct"])),
            notional_usd=Decimal(str(p["notional_usd"])),
            rationale=p.get("rationale"),
            entry_price=Decimal(str(p["entry_price"])),
            entry_price_date=datetime.now(UTC).date(),
        ))
    session.flush()
    return row


def test_index_empty_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "tacapes" in r.text
    assert "no missions yet" in r.text.lower()


def test_index_lists_done_mission_with_pnl(client, session):
    _insert_done_mission(
        session, statement="Test mission " * 5,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
    )
    session.commit()
    with patch.object(prices, "get_current_prices",
                      return_value={"NRG": Decimal("110.00")}):
        r = client.get("/")
    assert r.status_code == 200
    assert "NRG" in r.text or "+10" in r.text  # P&L shows up somewhere
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py::test_index_empty_renders -v`
Expected: 404 (no `/` route registered yet) or template-not-found.

- [ ] **Step 3: Implement the `/` route**

Edit `tacapes/dashboard/routes.py`:

```python
"""Route handlers, split out so each phase can append cleanly."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from . import prices
from .db import session_scope
from .db.repo import list_missions


def _compute_mission_pnl(mission, current_prices) -> dict[str, Any] | None:
    """For a 'done' mission, return {invested, current, pnl_pct, n_unpriced}.
    None if there are no priced positions to compute against."""
    if not mission.positions:
        return None
    invested = Decimal("0")
    current = Decimal("0")
    n_unpriced = 0
    for p in mission.positions:
        cur = current_prices.get(p.ticker)
        if p.entry_price is None or cur is None or p.entry_price == 0:
            n_unpriced += 1
            continue
        shares = p.notional_usd / p.entry_price
        invested += p.notional_usd
        current += shares * cur
    if invested == 0:
        return {"invested": 0, "current": 0, "pnl_pct": None, "n_unpriced": n_unpriced}
    pnl_pct = float((current - invested) / invested) * 100
    return {
        "invested": float(invested), "current": float(current),
        "pnl_pct": pnl_pct, "n_unpriced": n_unpriced,
    }


def register(app: FastAPI) -> None:
    templates = app.state.templates

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Any:
        from .db.repo import get_mission_with_positions
        with session_scope() as session:
            missions = list_missions(session)
            # Eager-load positions for done missions only.
            done_with_positions = []
            for m in missions:
                if m.status.value == "done":
                    full = get_mission_with_positions(session, m.id)
                    done_with_positions.append(full)
                else:
                    done_with_positions.append(m)

            # Collect tickers across all done missions for the price fetch.
            all_tickers = sorted({
                p.ticker
                for m in done_with_positions
                if m.status.value == "done"
                for p in m.positions
            })
            current = prices.get_current_prices(session, all_tickers)

            rows = []
            agg_invested = Decimal("0")
            agg_current = Decimal("0")
            agg_unpriced = 0
            agg_cost = Decimal("0")
            for m in done_with_positions:
                pnl = _compute_mission_pnl(m, current) if m.status.value == "done" else None
                if pnl is not None:
                    agg_invested += Decimal(str(pnl["invested"]))
                    agg_current += Decimal(str(pnl["current"]))
                    agg_unpriced += pnl["n_unpriced"]
                if m.cost_usd is not None:
                    agg_cost += m.cost_usd
                rows.append({"mission": m, "pnl": pnl})

            agg_pnl_pct = None
            if agg_invested > 0:
                agg_pnl_pct = float((agg_current - agg_invested) / agg_invested) * 100

        return templates.TemplateResponse(request, "index.html", {
            "rows": rows,
            "agg": {
                "invested": float(agg_invested),
                "current": float(agg_current),
                "pnl_pct": agg_pnl_pct,
                "n_unpriced": agg_unpriced,
                "cost": float(agg_cost),
            },
        })
```

- [ ] **Step 4: Write `index.html`**

```html
{% extends "base.html" %}
{% block title %}tacapes: history{% endblock %}
{% block body %}
<section>
  <div class="muted">
    {% if agg.invested > 0 %}
      invested ${{ "%.0f"|format(agg.invested) }} ·
      current ${{ "%.0f"|format(agg.current) }} ·
      {% if agg.pnl_pct is not none %}
        <span class="pnl {{ 'up' if agg.pnl_pct >= 0 else 'down' }}">
          {{ "%+.2f"|format(agg.pnl_pct) }}%
        </span>
      {% endif %}
      · ${{ "%.2f"|format(agg.cost) }} spent
      {% if agg.n_unpriced %} · {{ agg.n_unpriced }} unpriced positions{% endif %}
    {% else %}
      no priced positions yet
    {% endif %}
  </div>
</section>
<section>
  {% if rows %}
    <table class="history">
      <thead>
        <tr>
          <th>status</th>
          <th>statement</th>
          <th>created</th>
          <th>cost</th>
          <th>P&amp;L</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
          {% include "_mission_row.html" %}
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p class="muted">no missions yet. click <a href="/missions/new">+ new mission</a> to get started.</p>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 5: Write `_mission_row.html`**

```html
{% set m = row.mission %}
{% set pnl = row.pnl %}
<tr>
  <td><span class="badge {{ m.status.value }}">{{ m.status.value }}</span></td>
  <td>
    <a href="/missions/{{ m.id }}" class="statement-preview">
      {{ m.statement[:120] }}{% if m.statement|length > 120 %}…{% endif %}
    </a>
  </td>
  <td class="muted">{{ m.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
  <td>
    {% if m.cost_usd is not none %}${{ "%.2f"|format(m.cost_usd|float) }}{% else %}—{% endif %}
  </td>
  <td>
    {% if pnl and pnl.pnl_pct is not none %}
      <span class="pnl {{ 'up' if pnl.pnl_pct >= 0 else 'down' }}">
        {{ "%+.2f"|format(pnl.pnl_pct) }}%
      </span>
    {% else %}—{% endif %}
  </td>
  <td><a href="/missions/{{ m.id }}" class="btn">open</a></td>
</tr>
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py::test_index_empty_renders tests/dashboard/test_routes.py::test_index_lists_done_mission_with_pnl -v`
Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add tacapes/dashboard/routes.py tacapes/dashboard/templates/index.html tacapes/dashboard/templates/_mission_row.html tests/dashboard/test_routes.py
git commit -m "Add history page route + templates with aggregate P&L"
```

---

### Task 3.5: Mission detail page. done branch (`GET /missions/<id>`)

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Create: `tacapes/dashboard/templates/mission_detail.html`
- Create: `tacapes/dashboard/templates/_done.html`
- Modify: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_routes.py`:

```python
def test_mission_detail_done_renders_all_sections(client, session):
    row = _insert_done_mission(
        session, statement="Test mission " * 5,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
    )
    row.decomposition_json = {"sub_themes": [{"id": "s1", "name": "AI Power"}]}
    row.assessments_json = {"s1": {"candidates": [{"ticker": "NRG"}]}}
    row.shortlist_json = {"candidates": [{"ticker": "NRG", "conviction": 5}]}
    row.ta_outputs_json = {"NRG": {"final_decision": "Buy"}}
    row.memos_json = {"NRG": {"conviction": 5, "thesis_alignment": "aligned"}}
    session.commit()
    mission_id = row.id

    with patch.object(prices, "get_current_prices",
                      return_value={"NRG": Decimal("110.00")}):
        r = client.get(f"/missions/{mission_id}")
    assert r.status_code == 200
    body = r.text
    assert "AI Power" in body
    assert "NRG" in body
    assert "Buy" in body
    assert "aligned" in body
    assert "Chosen" in body
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py::test_mission_detail_done_renders_all_sections -v`
Expected: 404 (route not registered).

- [ ] **Step 3: Register the detail route in `routes.py`**

Append inside `register(app)`:

```python
    @app.get("/missions/{mission_id}", response_class=HTMLResponse)
    def mission_detail(request: Request, mission_id: str) -> Any:
        import uuid
        from .db.repo import get_mission_with_positions
        try:
            mid = uuid.UUID(mission_id)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        with session_scope() as session:
            m = get_mission_with_positions(session, mid)
            if m is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            current = {}
            pnl_per_position = {}
            if m.status.value == "done":
                tickers = sorted({p.ticker for p in m.positions})
                current = prices.get_current_prices(session, tickers)
                for p in m.positions:
                    cur = current.get(p.ticker)
                    if p.entry_price and cur and p.entry_price > 0:
                        pnl_per_position[p.ticker] = float(
                            (cur - p.entry_price) / p.entry_price * 100
                        )

            # Compute chosen-tickers set for the shortlist's "Chosen / Passed" tags.
            chosen = set()
            if m.portfolio_json:
                chosen = {p["ticker"] for p in m.portfolio_json.get("positions", [])}

        return templates.TemplateResponse(request, "mission_detail.html", {
            "m": m,
            "current": current,
            "pnl_per_position": pnl_per_position,
            "chosen": chosen,
        })
```

- [ ] **Step 4: Write `mission_detail.html`**

```html
{% extends "base.html" %}
{% block title %}tacapes: {{ m.statement[:40] }}{% endblock %}
{% block body %}
<p><a href="/" class="muted">← back</a></p>
<h1 style="font-size:18px">{{ m.statement }}</h1>
<p class="muted">
  budget ${{ "%.0f"|format(m.budget_usd|float) }} ·
  max {{ m.max_positions }} positions ·
  {{ m.horizon_months }}mo horizon ·
  created {{ m.created_at.strftime("%Y-%m-%d %H:%M") }}
  {% if m.cost_usd is not none %} · ${{ "%.2f"|format(m.cost_usd|float) }} spent{% endif %}
  · <span class="badge {{ m.status.value }}">{{ m.status.value }}</span>
</p>

{% if m.status.value in ("queued", "running") %}
  {% include "_spinner.html" %}
{% elif m.status.value == "failed" %}
  {% include "_failed.html" %}
{% else %}
  {% include "_done.html" %}
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Write `_done.html`**

```html
<section>
  <h2>sub-theses</h2>
  {% if m.decomposition_json and m.decomposition_json.get("sub_themes") %}
    <ul>
      {% for st in m.decomposition_json["sub_themes"] %}
        <li>
          <strong>{{ st.get("name") or st.get("title") or st.get("id") }}</strong>
          {% if st.get("description") %}<div class="muted">{{ st["description"] }}</div>{% endif %}
        </li>
      {% endfor %}
    </ul>
  {% else %}<p class="muted">no sub-theses recorded.</p>{% endif %}
</section>

<section>
  <h2>shortlist</h2>
  {% if m.shortlist_json and m.shortlist_json.get("candidates") %}
    <table class="history">
      <thead><tr><th>ticker</th><th>conviction</th><th>status</th></tr></thead>
      <tbody>
      {% for c in m.shortlist_json["candidates"] %}
        <tr>
          <td>{{ c.get("ticker") }}</td>
          <td>{{ c.get("conviction", "—") }}</td>
          <td>
            {% if c.get("ticker") in chosen %}
              <span class="badge done">Chosen</span>
            {% else %}
              <span class="badge queued">Passed</span>
            {% endif %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% else %}<p class="muted">no shortlist recorded.</p>{% endif %}
</section>

<section>
  <h2>reports</h2>
  {% if m.memos_json %}
    {% for ticker, memo in m.memos_json.items() %}
      <details class="report">
        <summary>
          <strong>{{ ticker }}</strong>
          · conviction {{ memo.get("conviction", "—") }},
          alignment {{ memo.get("thesis_alignment", "—") }}
        </summary>
        <h4>memo</h4>
        <pre>{{ memo | tojson(indent=2) }}</pre>
        {% if m.ta_outputs_json and m.ta_outputs_json.get(ticker) %}
          <h4>TradingAgents debate</h4>
          <pre>{{ m.ta_outputs_json[ticker] | tojson(indent=2) }}</pre>
        {% endif %}
      </details>
    {% endfor %}
  {% else %}<p class="muted">no reports recorded.</p>{% endif %}
</section>

<section>
  <h2>position breakdown</h2>
  <table class="history">
    <thead>
      <tr><th>ticker</th><th>weight</th><th>notional</th><th>entry</th><th>current</th><th>P&amp;L</th></tr>
    </thead>
    <tbody>
      {% for p in m.positions %}
      <tr>
        <td>{{ p.ticker }}</td>
        <td>{{ "%.1f"|format(p.weight_pct|float * 100) }}%</td>
        <td>${{ "%.0f"|format(p.notional_usd|float) }}</td>
        <td>
          {% if p.entry_price is not none %}
            ${{ "%.2f"|format(p.entry_price|float) }}
            <span class="muted">({{ p.entry_price_date }})</span>
          {% else %}—{% endif %}
        </td>
        <td>
          {% set c = current.get(p.ticker) %}
          {% if c is not none %}${{ "%.2f"|format(c|float) }}{% else %}—{% endif %}
        </td>
        <td>
          {% set pp = pnl_per_position.get(p.ticker) %}
          {% if pp is not none %}
            <span class="pnl {{ 'up' if pp >= 0 else 'down' }}">{{ "%+.2f"|format(pp) }}%</span>
          {% else %}—{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if m.portfolio_json and m.portfolio_json.get("cash_reserve_pct") %}
    <p class="muted">cash reserve: {{ "%.1f"|format(m.portfolio_json["cash_reserve_pct"] * 100) }}%</p>
  {% endif %}
</section>
```

- [ ] **Step 6: Write minimal placeholders for `_spinner.html` and `_failed.html`**

We need these to exist so the `mission_detail.html` `{% include %}` doesn't fail for `done` missions whose template path checks them. They get fleshed out in Phase 4/5.

`_spinner.html`:

```html
<section><div class="muted"><span class="spinner"></span> in progress…</div></section>
```

`_failed.html`:

```html
<div class="failed-panel">this run failed.</div>
```

- [ ] **Step 7: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py -v`
Expected: all 3 tests pass.

- [ ] **Step 8: Commit**

```bash
git add tacapes/dashboard/routes.py tacapes/dashboard/templates/mission_detail.html tacapes/dashboard/templates/_done.html tacapes/dashboard/templates/_spinner.html tacapes/dashboard/templates/_failed.html tests/dashboard/test_routes.py
git commit -m "Add mission detail page (done branch) with all stage sections"
```

---

### Task 3.6: Manual price refresh

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Modify: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_routes.py`:

```python
def test_prices_refresh_invalidates_cache(client, session):
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("100"),
        fetched_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post("/prices/refresh", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    with session_scope() as s:
        assert s.get(PriceQuote, "NRG") is None
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py::test_prices_refresh_invalidates_cache -v`
Expected: 404 (no `/prices/refresh` yet).

- [ ] **Step 3: Register the route in `routes.py`**

Append inside `register(app)`:

```python
    @app.post("/prices/refresh")
    def prices_refresh() -> Any:
        from fastapi.responses import RedirectResponse
        with session_scope() as session:
            prices.invalidate_price_cache(session)
        return RedirectResponse("/", status_code=303)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/routes.py tests/dashboard/test_routes.py
git commit -m "Add manual price-refresh route"
```

---

## Phase 4: New Mission From The UI

### Task 4.1: Mission runner. pipeline → DB writes

**Files:**
- Modify: `tacapes/dashboard/runners.py` (full rewrite)
- Create: `tests/dashboard/test_runners.py`

- [ ] **Step 1: Write the failing test**

`tests/dashboard/test_runners.py`:

```python
"""mission runner: runs the pipeline (mocked) and writes DB rows."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from tacapes.dashboard import runners, prices
from tacapes.dashboard.db import session_scope
from tacapes.dashboard.db.models import Mission, MissionStatus, Position
from tacapes.dashboard.db.repo import insert_mission


def _new_mission_id(session) -> uuid.UUID:
    m = insert_mission(
        session,
        statement="Buy nuclear power names benefiting from AI/data center demand " * 2,
        budget_usd=Decimal("20000"),
        max_positions=2,
        max_position_pct=Decimal("0.4"),
        horizon_months=12,
        sectors_excluded=[],
        allow_shorts=False,
    )
    session.flush()
    return m.id


def _fake_pipeline_result():
    """Mimics the LangGraph final-state dict that `build_graph().invoke()` returns."""
    return {
        "decomposition": {"sub_themes": [{"id": "s1", "name": "AI Power"}]},
        "subtheme_assessments": {"s1": {"candidates": [{"ticker": "NRG"}]}},
        "shortlist": {"candidates": [{"ticker": "NRG", "conviction": 5}]},
        "ta_outputs": {"NRG": {"final_decision": "Buy"}},
        "memos": {"NRG": {"conviction": 5, "thesis_alignment": "aligned"}},
        "portfolio": {
            "mission_id": "x", "mode": "cold_start", "total_budget_usd": 20000,
            "positions": [
                {"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                 "rationale": "t", "is_short": False}
            ],
            "correlation_map": [], "cash_reserve_pct": 0.0, "rationale": "t",
        },
    }


def test_make_mission_job_writes_done_row_and_positions(session):
    mid = _new_mission_id(session)
    session.commit()

    with patch.object(runners, "_invoke_pipeline", return_value=_fake_pipeline_result()), \
         patch.object(prices, "snapshot_entry_price",
                      return_value=(Decimal("95.42"), None)):
        fn = runners.make_mission_job(mid)
        fn(lambda msg: None)

    with session_scope() as s:
        m = s.get(Mission, mid)
        assert m.status == MissionStatus.done
        assert m.portfolio_json["positions"][0]["ticker"] == "NRG"
        positions = s.query(Position).filter_by(mission_id=mid).all()
        assert len(positions) == 1
        assert positions[0].entry_price == Decimal("95.42")


def test_make_mission_job_marks_failed_on_exception(session):
    mid = _new_mission_id(session)
    session.commit()

    def boom(_mission):
        raise RuntimeError("pipeline blew up")

    with patch.object(runners, "_invoke_pipeline", side_effect=boom):
        fn = runners.make_mission_job(mid)
        fn(lambda msg: None)

    with session_scope() as s:
        m = s.get(Mission, mid)
        assert m.status == MissionStatus.failed
        assert m.error_message and "pipeline blew up" in m.error_message
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_runners.py -v`
Expected: AttributeError / ImportError on `runners.make_mission_job` / `runners._invoke_pipeline`.

- [ ] **Step 3: Rewrite `tacapes/dashboard/runners.py`**

```python
"""Job bodies for the dashboard JobRunner.

`make_mission_job(mission_id)` returns a `fn(progress) -> result_ref` closure
that:
  1. Loads the queued Mission row from the DB.
  2. Marks it running.
  3. Runs the existing LangGraph pipeline.
  4. Snapshots entry prices via yfinance.
  5. Writes the final state to the DB (mark_done + insert_positions).
  6. On any exception, mark_failed with a one-line message."""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Callable

from . import prices
from .db import session_scope
from .db.models import Mission
from .db.repo import insert_positions, mark_done, mark_failed, mark_running
from .jobs import JobFn

log = logging.getLogger(__name__)


def _invoke_pipeline(mission: Mission) -> dict:
    """Build a Pydantic Mission from the DB row, run the graph, return the
    final state dict. Split out so tests can patch this single seam."""
    from ..graph import build_graph
    from ..schemas import Mission as PMission, MissionConstraints

    pmission = PMission(
        id=str(mission.id),
        statement=mission.statement,
        budget_usd=float(mission.budget_usd),
        constraints=MissionConstraints(
            max_position_pct=float(mission.max_position_pct),
            max_positions=int(mission.max_positions),
            sectors_excluded=list(mission.sectors_excluded or []),
            allow_shorts=bool(mission.allow_shorts),
            time_horizon_months=int(mission.horizon_months),
        ),
        created_at=mission.created_at,
    )
    final = build_graph().invoke({"mission": pmission})
    return final


def _serialize(val) -> dict | None:
    """Convert a Pydantic model or dict to a JSON-safe dict; return None for None."""
    if val is None:
        return None
    if hasattr(val, "model_dump"):
        return val.model_dump(mode="json")
    if isinstance(val, dict):
        return {k: _serialize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize(v) for v in val]  # type: ignore[return-value]
    return val


def make_mission_job(mission_id: uuid.UUID) -> JobFn:
    """Build a JobFn that runs the pipeline for the given mission_id."""

    def fn(progress: Callable[[str], None]) -> str:
        from ..cost import _TRACKER

        with session_scope() as s:
            mission = s.get(Mission, mission_id)
            if mission is None:
                raise LookupError(f"mission {mission_id} not in DB")
            mark_running(s, mission_id)

        cost_before = _TRACKER.snapshot().total_usd()

        try:
            with session_scope() as s:
                mission = s.get(Mission, mission_id)
                progress("pipeline starting")
                final = _invoke_pipeline(mission)
                progress("snapshotting entry prices")

                portfolio = _serialize(final.get("portfolio")) or {}
                position_rows = []
                for p in portfolio.get("positions", []):
                    price, price_date = prices.snapshot_entry_price(p["ticker"])
                    position_rows.append({
                        "ticker": p["ticker"],
                        "weight_pct": Decimal(str(p["weight_pct"])),
                        "notional_usd": Decimal(str(p["notional_usd"])),
                        "rationale": p.get("rationale"),
                        "entry_price": price,
                        "entry_price_date": price_date,
                    })

                mark_done(
                    s, mission_id,
                    decomposition_json=_serialize(final.get("decomposition")),
                    assessments_json=_serialize(final.get("subtheme_assessments")),
                    shortlist_json=_serialize(final.get("shortlist")),
                    ta_outputs_json=_serialize(final.get("ta_outputs")),
                    memos_json=_serialize(final.get("memos")),
                    portfolio_json=portfolio,
                    cost_usd=Decimal(f"{_TRACKER.snapshot().total_usd() - cost_before:.2f}"),
                )
                insert_positions(s, mission_id, position_rows)

            return f"mission {mission_id} done"

        except Exception as e:  # noqa: BLE001. recorded, not re-raised
            log.exception("mission %s failed", mission_id)
            with session_scope() as s:
                mark_failed(s, mission_id, f"{type(e).__name__}: {e}")
            return f"mission {mission_id} failed"

    return fn
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/dashboard/test_runners.py -v`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/runners.py tests/dashboard/test_runners.py
git commit -m "Add mission runner: pipeline → DB writes, failed-state handling"
```

---

### Task 4.2: New-mission form (`GET /missions/new`)

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Create: `tacapes/dashboard/templates/mission_new.html`
- Modify: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_routes.py`:

```python
def test_mission_new_renders_form(client):
    r = client.get("/missions/new")
    assert r.status_code == 200
    body = r.text
    for field in ("statement", "budget_usd", "max_positions",
                  "max_position_pct", "horizon_months",
                  "sectors_excluded", "allow_shorts"):
        assert field in body
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py::test_mission_new_renders_form -v`
Expected: 404.

- [ ] **Step 3: Register the route**

Append inside `register(app)`:

```python
    @app.get("/missions/new", response_class=HTMLResponse)
    def mission_new(request: Request) -> Any:
        return templates.TemplateResponse(request, "mission_new.html", {})
```

- [ ] **Step 4: Write `mission_new.html`**

```html
{% extends "base.html" %}
{% block title %}tacapes: new mission{% endblock %}
{% block body %}
<p><a href="/" class="muted">← back</a></p>
<h1 style="font-size:18px">new mission</h1>
<form method="post" action="/missions" style="max-width:600px">
  <p>
    <label>statement<br>
      <textarea name="statement" required minlength="20" rows="4" style="width:100%"
        placeholder="Buy nuclear power names positioned to win AI/data center power contracts through 2027"></textarea>
    </label>
  </p>
  <p>
    <label>budget_usd <input type="number" name="budget_usd" value="20000" min="1" step="1" required></label>
  </p>
  <p>
    <label>max_positions <input type="number" name="max_positions" value="5" min="1" step="1" required></label>
  </p>
  <p>
    <label>max_position_pct <input type="number" name="max_position_pct" value="0.4" min="0.01" max="1.0" step="0.01" required></label>
  </p>
  <p>
    <label>horizon_months <input type="number" name="horizon_months" value="12" min="1" step="1" required></label>
  </p>
  <p>
    <label>sectors_excluded (comma-separated)<br>
      <input type="text" name="sectors_excluded" placeholder="e.g. crypto,gambling" style="width:100%">
    </label>
  </p>
  <p>
    <label><input type="checkbox" name="allow_shorts" value="1"> allow shorts</label>
  </p>
  <p>
    <button type="submit" class="btn btn-primary">run mission</button>
  </p>
</form>
{% endblock %}
```

- [ ] **Step 5: Run test, verify pass**

Run: `pytest tests/dashboard/test_routes.py::test_mission_new_renders_form -v`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add tacapes/dashboard/routes.py tacapes/dashboard/templates/mission_new.html tests/dashboard/test_routes.py
git commit -m "Add new-mission form"
```

---

### Task 4.3: Mission submission (`POST /missions`)

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Modify: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_routes.py`:

```python
def test_post_missions_validates_and_enqueues(client, session):
    """The sync fake JobRunner will run the job immediately, so we patch the
    pipeline-invocation seam to return a known final state."""
    from tacapes.dashboard import runners

    payload = {
        "statement": "Buy nuclear names benefiting from AI/data center demand " * 2,
        "budget_usd": "20000",
        "max_positions": "2",
        "max_position_pct": "0.4",
        "horizon_months": "12",
        "sectors_excluded": "",
        "allow_shorts": "1",
    }
    fake_final = {
        "decomposition": {"sub_themes": []},
        "subtheme_assessments": {},
        "shortlist": {"candidates": []},
        "ta_outputs": {},
        "memos": {},
        "portfolio": {
            "mission_id": "x", "mode": "cold_start", "total_budget_usd": 20000,
            "positions": [], "correlation_map": [], "cash_reserve_pct": 1.0,
            "rationale": "all cash",
        },
    }
    with patch.object(runners, "_invoke_pipeline", return_value=fake_final), \
         patch.object(prices, "snapshot_entry_price", return_value=(None, None)):
        r = client.post("/missions", data=payload, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/missions/")

    with session_scope() as s:
        rows = s.query(Mission).all()
        assert len(rows) == 1
        assert rows[0].allow_shorts is True
        # Sync JobRunner ran the job synchronously → done.
        assert rows[0].status == MissionStatus.done


def test_post_missions_rejects_short_statement(client):
    r = client.post("/missions", data={
        "statement": "too short",
        "budget_usd": "20000",
        "max_positions": "2",
        "max_position_pct": "0.4",
        "horizon_months": "12",
    }, follow_redirects=False)
    assert r.status_code == 400
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py::test_post_missions_validates_and_enqueues -v`
Expected: 404 or method-not-allowed.

- [ ] **Step 3: Register the route**

Append inside `register(app)`:

```python
    @app.post("/missions")
    def post_missions(
        request: Request,
        statement: str = Form(...),
        budget_usd: float = Form(...),
        max_positions: int = Form(...),
        max_position_pct: float = Form(...),
        horizon_months: int = Form(...),
        sectors_excluded: str = Form(""),
        allow_shorts: str | None = Form(None),
    ) -> Any:
        from decimal import Decimal
        from fastapi import HTTPException
        from fastapi.responses import RedirectResponse
        from pydantic import ValidationError
        from ..schemas import Mission as PMission, MissionConstraints
        from .db.repo import insert_mission
        from .runners import make_mission_job

        sectors = [s.strip() for s in sectors_excluded.split(",") if s.strip()]
        try:
            constraints = MissionConstraints(
                max_position_pct=max_position_pct,
                max_positions=max_positions,
                sectors_excluded=sectors,
                allow_shorts=bool(allow_shorts),
                time_horizon_months=horizon_months,
            )
            PMission(statement=statement, budget_usd=budget_usd, constraints=constraints)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        with session_scope() as session:
            row = insert_mission(
                session,
                statement=statement,
                budget_usd=Decimal(str(budget_usd)),
                max_positions=max_positions,
                max_position_pct=Decimal(str(max_position_pct)),
                horizon_months=horizon_months,
                sectors_excluded=sectors,
                allow_shorts=bool(allow_shorts),
            )
            session.flush()
            mission_id = row.id

        runner = request.app.state.job_runner
        runner.submit(
            kind="mission",
            target=statement[:80],
            fn=make_mission_job(mission_id),
        )
        return RedirectResponse(f"/missions/{mission_id}", status_code=303)
```

Make sure the imports at the top of `routes.py` include `from fastapi import Form`. add it.

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/routes.py tests/dashboard/test_routes.py
git commit -m "Add POST /missions: validate, enqueue, redirect to detail"
```

---

### Task 4.4: Spinner branch + status polling

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Modify: `tacapes/dashboard/templates/_spinner.html`
- Modify: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_routes.py`:

```python
def test_mission_detail_running_shows_spinner(client, session):
    row = Mission(
        statement="Test " * 10, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.running, created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(row); session.commit()
    r = client.get(f"/missions/{row.id}")
    assert r.status_code == 200
    assert "in progress" in r.text.lower() or "spinner" in r.text.lower()


def test_status_endpoint_returns_redirect_when_done(client, session):
    row = Mission(
        statement="Test " * 10, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.done, created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    session.add(row); session.commit()
    r = client.get(f"/missions/{row.id}/status")
    assert r.status_code == 200
    assert r.headers.get("HX-Redirect") == f"/missions/{row.id}"


def test_status_endpoint_returns_spinner_when_running(client, session):
    row = Mission(
        statement="Test " * 10, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.running, created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(row); session.commit()
    r = client.get(f"/missions/{row.id}/status")
    assert r.status_code == 200
    assert "HX-Redirect" not in r.headers
    assert "in progress" in r.text.lower()
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py -v -k "spinner or status_endpoint"`
Expected: 404 on `/missions/.../status`.

- [ ] **Step 3: Flesh out `_spinner.html` with HTMX polling**

```html
<section>
  <div id="status-poll"
       hx-get="/missions/{{ m.id }}/status"
       hx-trigger="every 3s"
       hx-swap="outerHTML">
    <div class="muted"><span class="spinner"></span> in progress…</div>
  </div>
</section>
```

- [ ] **Step 4: Register the status route in `routes.py`**

Append inside `register(app)`:

```python
    @app.get("/missions/{mission_id}/status", response_class=HTMLResponse)
    def mission_status(request: Request, mission_id: str) -> Any:
        import uuid
        from fastapi import HTTPException
        from fastapi.responses import Response
        try:
            mid = uuid.UUID(mission_id)
        except ValueError:
            raise HTTPException(status_code=404)
        with session_scope() as session:
            m = session.get(Mission, mid)
            if m is None:
                raise HTTPException(status_code=404)
            terminal = m.status.value in ("done", "failed")
        if terminal:
            return Response(
                content="", headers={"HX-Redirect": f"/missions/{mid}"}
            )
        return HTMLResponse(
            '<div class="muted"><span class="spinner"></span> in progress…</div>'
        )
```

Also add `from .db.models import Mission` to the imports at the top of `routes.py` if not already present.

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tacapes/dashboard/routes.py tacapes/dashboard/templates/_spinner.html tests/dashboard/test_routes.py
git commit -m "Add HTMX polling for running-mission status"
```

---

## Phase 5: Failure And Delete

### Task 5.1: Failed branch on the detail page

**Files:**
- Modify: `tacapes/dashboard/templates/_failed.html`
- Modify: `tests/dashboard/test_routes.py`

(The runner already writes `status='failed'`. Task 4.1 covered this. We just need to render it nicely.)

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_routes.py`:

```python
def test_mission_detail_failed_shows_simple_panel(client, session):
    row = Mission(
        statement="Test " * 10, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.failed,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        error_message="RuntimeError: pipeline blew up",
    )
    session.add(row); session.commit()
    r = client.get(f"/missions/{row.id}")
    assert r.status_code == 200
    body = r.text.lower()
    assert "this run failed" in body
    # Per spec: no traceback, no reason shown.
    assert "runtimeerror" not in body
    assert "blew up" not in body
    # Delete button is visible on failed runs.
    assert "delete" in body
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py::test_mission_detail_failed_shows_simple_panel -v`
Expected: assertion failure (no "delete" yet, or "this run failed" not present).

- [ ] **Step 3: Update `_failed.html`**

```html
<div class="failed-panel">
  <p>This run failed.</p>
  <form method="post" action="/missions/{{ m.id }}/delete"
        onsubmit="return confirm('Delete this mission?')">
    <button type="submit" class="btn btn-danger">delete</button>
  </form>
</div>
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py -v`
Expected: pass (the delete route 404s but the button just needs to be in HTML; we wire the route in Task 5.4).

- [ ] **Step 5: Commit**

```bash
git add tacapes/dashboard/templates/_failed.html tests/dashboard/test_routes.py
git commit -m "Render failed missions as a simple panel with delete button"
```

---

### Task 5.2: Delete mission (`POST /missions/<id>/delete`)

**Files:**
- Modify: `tacapes/dashboard/routes.py`
- Modify: `tacapes/dashboard/templates/_mission_row.html`
- Modify: `tacapes/dashboard/templates/_done.html`
- Modify: `tests/dashboard/test_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/dashboard/test_routes.py`:

```python
def test_delete_mission_removes_row_and_positions(client, session, tmp_path, monkeypatch):
    # Point tacapes_home at tmp_path so we exercise the folder cleanup safely.
    from tacapes import config
    monkeypatch.setattr(config, "tacapes_home", lambda: tmp_path)

    row = _insert_done_mission(
        session, statement="Test " * 10,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
    )
    session.commit()
    mission_id = row.id

    folder = tmp_path / "portfolios" / str(mission_id)
    folder.mkdir(parents=True)
    (folder / "mission.json").write_text("{}")

    r = client.post(f"/missions/{mission_id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    with session_scope() as s:
        assert s.get(Mission, mission_id) is None
        assert s.query(Position).filter_by(mission_id=mission_id).count() == 0
    assert not folder.exists()


def test_delete_running_mission_returns_409(client, session):
    row = Mission(
        statement="Test " * 10, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.running, created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(row); session.commit()
    r = client.post(f"/missions/{row.id}/delete", follow_redirects=False)
    assert r.status_code == 409
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/dashboard/test_routes.py -v -k delete`
Expected: 404 (route not registered).

- [ ] **Step 3: Register the route**

Append inside `register(app)`:

```python
    @app.post("/missions/{mission_id}/delete")
    def delete_mission_route(mission_id: str) -> Any:
        import shutil
        import uuid
        from fastapi import HTTPException
        from fastapi.responses import RedirectResponse
        from ..config import tacapes_home
        from .db.repo import delete_mission
        try:
            mid = uuid.UUID(mission_id)
        except ValueError:
            raise HTTPException(status_code=404)
        with session_scope() as session:
            m = session.get(Mission, mid)
            if m is None:
                raise HTTPException(status_code=404)
            if m.status.value == "running":
                raise HTTPException(status_code=409, detail="cannot delete a running mission")
            delete_mission(session, mid)
        folder = tacapes_home() / "portfolios" / str(mid)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        return RedirectResponse("/", status_code=303)
```

- [ ] **Step 4: Add a delete button to `_mission_row.html`**

Replace the last `<td>` (the `<a class="btn">open</a>` cell) with:

```html
<td>
  <a href="/missions/{{ m.id }}" class="btn">open</a>
  {% if m.status.value != "running" %}
    <form method="post" action="/missions/{{ m.id }}/delete" style="display:inline"
          onsubmit="return confirm('Delete this mission?')">
      <button type="submit" class="btn btn-danger">delete</button>
    </form>
  {% endif %}
</td>
```

- [ ] **Step 5: Add a delete button at the bottom of `_done.html`**

Append at the end of `_done.html`:

```html
<section>
  <form method="post" action="/missions/{{ m.id }}/delete"
        onsubmit="return confirm('Delete this mission?')">
    <button type="submit" class="btn btn-danger">delete this mission</button>
  </form>
</section>
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/dashboard/test_routes.py -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tacapes/dashboard/routes.py tacapes/dashboard/templates/_mission_row.html tacapes/dashboard/templates/_done.html tests/dashboard/test_routes.py
git commit -m "Add delete-mission route, button in row and detail page, 409 if running"
```

---

### Task 5.3: End-to-end smoke + cleanup

**Files:** (no new code. manual verification of the full slice)

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/mohamedalimanai/tacapes-v2 && pytest -q`
Expected: all tests pass (existing + new dashboard tests).

- [ ] **Step 2: Lint**

Run: `ruff check tacapes/`
Expected: clean, or fix any remaining issues inline.

- [ ] **Step 3: End-to-end manual smoke test**

```
docker compose up -d db
tacapes dashboard --port 8732
# In browser:
# 1. visit http://127.0.0.1:8732. see backfilled historical missions with P&L
# 2. click an old mission. verify subtheses / shortlist / reports / positions render
# 3. click + new mission. fill the form with a small budget and submit
# 4. spinner page polls; do NOT submit a real expensive mission unless you want to pay
#    (test by killing the worker mid-run or using a tiny mission to confirm UX)
# 5. when done, see it in the history with badge=done and P&L
# 6. click delete on a test row. confirm the folder is gone too
# 7. click refresh prices. verify the cache is invalidated (timestamp resets)
```

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git diff --cached --quiet || git commit -m "Final lint pass"
```

- [ ] **Step 5: Final spec-coverage check**

Re-read the spec one more time. For each section, point to the task that implements it. Append any uncovered requirements as new tasks below this one.

- [ ] **Step 6: Push branch**

```bash
git push -u origin history-dashboard
```

(Open a PR yourself when ready. Not automated by this plan.)

---

## Spec Coverage Map

| Spec section | Implemented by |
| --- | --- |
| §3 architecture (Docker + FastAPI + worker) | Task 1.2, 1.5, 4.1 |
| §4.1 missions table | Task 1.3, 1.4 |
| §4.2 positions table | Task 1.3, 1.4 |
| §4.3 price_quotes table | Task 1.3, 1.4 |
| §4.4 alembic migrations | Task 1.4 |
| §5.1 create mission flow | Task 4.1, 4.3 |
| §5.2 dashboard render + price refresh | Task 3.1, 3.4 |
| §5.3 mission detail (queued/running/done/failed) | Tasks 3.5, 4.4, 5.1 |
| §5.4 delete mission | Task 5.2 |
| §5.5 first-launch backfill (incl. historical prices) | Task 2.1, 2.2, 2.3 |
| §6 pages and routes | Tasks 3.2, 3.4, 3.5, 3.6, 4.2, 4.3, 4.4, 5.2 |
| §7 error handling (failed/yfinance miss/db down/recovery) | Tasks 4.1 (failed), 2.1+3.1 (yfinance NULL), 1.7 (db reachable), 1.7 (orphan recovery) |
| §8 testing | conftest + every TDD step |
| §9 dependencies | Task 1.1 |
| §10 layout | All file paths in tasks |
| §11 phased build plan | Phases 1-5 |

---

## Notes for the executor

- **Frequent commits.** Every task ends in a commit. Don't batch tasks.
- **Run tests after every code step.** If TDD says fail-first, actually run it and see it fail before implementing.
- **If yfinance returns weird shapes** (DataFrame columns differ between versions), let the test patch it; the production code already tolerates `None` and empty DataFrames.
- **If alembic --autogenerate misses an index**, edit the generated migration file by hand. The migration is what gets committed, not the autogenerate command.
- **Do not import from `tacapes.fund`, `tacapes.refresh`, or `tacapes.proposals`** anywhere in the new dashboard code. Those modules belong to the deferred fund slice.
- **Do not modify `tacapes/dashboard/jobs.py`**. Its `JobRunner` shape is exactly what the new runner needs.
