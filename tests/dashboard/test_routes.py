"""Route tests using FastAPI TestClient against the real test DB."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tacapes.dashboard.app import create_app
from tacapes.dashboard.db import session_scope
from tacapes.dashboard.db.models import Mission, MissionStatus, Position, PriceQuote
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


def test_mission_detail_done_renders_all_sections(client, session):
    row = _insert_done_mission(
        session, statement="Test mission " * 5,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
    )
    row.decomposition_json = {"sub_themes": [{"id": "s1", "name": "AI Power"}]}
    row.assessments_json = {"s1": {"candidates": [{"ticker": "NRG"}]}}
    row.shortlist_json = {"candidates": [{"ticker": "NRG", "conviction": 5}]}
    row.ta_outputs_json = {"NRG": {
        "ticker": "NRG", "mission_id": str(row.id), "trade_date": "2026-05-12",
        "rating": "Buy",
        "full_decision_markdown": "## Decision\nBuy NRG.\n\n**Reason:** thesis intact.",
        "market_report": "Market is constructive. Volume up 12%.",
        "investment_plan": "Enter at market open.",
        "price_target": 175.0, "time_horizon": "12m",
    }}
    row.memos_json = {"NRG": {
        "ticker": "NRG",
        "thesis_one_liner": "AI power demand drives nuclear-adjacent names.",
        "conviction": 5,
        "thesis_alignment": "aligned",
        "reconciliation_notes": "TA Buy + thesis intact: aligned with no caveats.",
        "drivers": [
            {"name": "Data-center power demand", "importance": "primary",
             "description": "AI training capex pulls grid forward."},
        ],
        "risks": [
            {"name": "Regulatory delays", "severity": "medium", "likelihood": "low",
             "description": "Permitting can slip a quarter or two."},
        ],
        "catalysts": [
            {"name": "Q3 earnings", "impact": "medium",
             "description": "Guidance update."},
        ],
        "valuation": {
            "base":    {"label": "base",    "methodology": "DCF", "price_target": 175.0},
            "bear":    {"label": "bear",    "methodology": "DCF", "price_target": 130.0},
            "bull":    {"label": "bull",    "methodology": "DCF", "price_target": 220.0},
            "current": {"label": "current", "methodology": "spot", "price_target": None},
        },
        "thesis_breakers": [
            "NRG reports gross margin below 25% in any of the next 4 quarters",
        ],
    }}
    session.commit()
    mission_id = row.id

    with patch.object(prices, "get_current_prices",
                      return_value={"NRG": Decimal("110.00")}):
        r = client.get(f"/missions/{mission_id}")
    assert r.status_code == 200
    body = r.text

    # Spine sections still render.
    assert "AI Power" in body
    assert "NRG" in body
    assert "Chosen" in body

    # Memo: structured content (not JSON).
    assert "Conviction: 5/5" in body
    assert "conviction-good" in body, "conviction 5 must carry the 'good' badge class"
    assert "alignment-good" in body, "thesis_alignment=aligned must carry the 'good' badge class"
    assert "aligned" in body
    assert "Reconciliation notes" in body
    assert "TA Buy + thesis intact" in body
    assert "Data-center power demand" in body
    assert "Regulatory delays" in body
    assert "Q3 earnings" in body
    assert "Thesis breakers" in body
    assert "gross margin below 25%" in body
    assert "Valuation" in body
    assert "$175.00" in body

    # TA debate: rendered with semantic badge + prose, no JSON dump.
    assert "PM decision: Buy" in body
    assert "rating-good" in body
    assert "Buy NRG." in body
    assert "Market is constructive" in body

    # Raw JSON dump is gone.
    assert "&#34;final_decision&#34;" not in body
    assert "<pre>{" not in body


def test_mission_detail_404_invalid_uuid(client):
    r = client.get("/missions/not-a-uuid")
    assert r.status_code == 404


def test_mission_detail_404_unknown_id(client):
    r = client.get("/missions/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


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


def test_mission_new_renders_form(client):
    r = client.get("/missions/new")
    assert r.status_code == 200
    body = r.text
    for field in ("statement", "budget_usd", "max_positions",
                  "max_position_pct", "horizon_months",
                  "sectors_excluded", "allow_shorts"):
        assert field in body


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


def test_status_endpoint_running_response_includes_polling_attrs(client, session):
    """Regression: the in-progress fragment must re-include hx-get/hx-trigger
    so HTMX keeps polling. Without this, the spinner shows forever after the
    first tick."""
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
    assert 'hx-get=' in r.text
    assert 'hx-trigger=' in r.text
    assert "every 3s" in r.text
