"""Repo function tests. Each function in repo.py gets at least one test."""
from __future__ import annotations

from datetime import datetime, timezone
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
                "entry_price_date": datetime(2026, 5, 31, tzinfo=timezone.utc).date(),
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
