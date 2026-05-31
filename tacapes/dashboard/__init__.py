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

    # First-launch backfill of existing ~/.tacapes/portfolios/.
    from .backfill import backfill_from_disk
    from .db.repo import list_missions
    from ..config import tacapes_home

    with session_scope() as session:
        if not list_missions(session):
            portfolios = tacapes_home() / "portfolios"
            log.info("missions table empty; backfilling from %s", portfolios)
            n = backfill_from_disk(session, portfolios)
            log.info("backfill: inserted %d mission(s)", n)
