"""Route tests using FastAPI TestClient against the real test DB."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tacapes.dashboard.app import create_app
from tacapes.dashboard.db import session_scope
from tacapes.dashboard.db.models import Mission, MissionStatus, Position
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
