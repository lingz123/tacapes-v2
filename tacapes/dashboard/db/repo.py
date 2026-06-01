"""Thin query helpers over the SQLAlchemy models. Each function takes a
Session and does ONE focused unit of work. All datetimes are timezone-aware UTC."""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
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
    sectors_excluded: list,
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
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    return row


def mark_running(session: Session, mission_id: uuid.UUID) -> None:
    row = session.get(Mission, mission_id)
    if row is None:
        raise LookupError(f"mission {mission_id} not found")
    row.status = MissionStatus.running
    row.started_at = datetime.now(timezone.utc)


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
    row.completed_at = datetime.now(timezone.utc)
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
    row.completed_at = datetime.now(timezone.utc)
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
    stmt = select(Mission).where(Mission.status == MissionStatus.running)
    rows = list(session.scalars(stmt))
    for row in rows:
        row.status = MissionStatus.failed
        row.completed_at = datetime.now(timezone.utc)
        row.error_message = "process restart"
    return len(rows)
