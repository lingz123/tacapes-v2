"""JSON API tests for the React-SPA-facing endpoints.

Mirrors test_routes.py for the HTML side. Both stay green during Phases
2-5; Phase 6 deletes test_routes.py.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tacapes.dashboard import prices
from tacapes.dashboard.app import create_app
from tacapes.dashboard.db import session_scope
from tacapes.dashboard.db.models import Mission, MissionStatus, Position, PriceQuote


class _SyncJobRunner:
    """Runs jobs immediately so the API's POST flow can be tested end-to-end."""
    def submit(self, *, kind, target, fn):
        fn(lambda msg: None)
    def list_jobs(self):
        return []
    def drain_completed(self):
        return set()


@pytest.fixture
def client():
    return TestClient(create_app(job_runner=_SyncJobRunner()))


def _insert_done_mission(
    session,
    *,
    statement,
    positions,
    decomposition_json=None,
    assessments_json=None,
    shortlist_json=None,
    ta_outputs_json=None,
    memos_json=None,
    portfolio_json=None,
):
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
        portfolio_json=portfolio_json
        or {"positions": positions, "cash_reserve_pct": 0.0, "rationale": "t"},
        decomposition_json=decomposition_json,
        assessments_json=assessments_json,
        shortlist_json=shortlist_json,
        ta_outputs_json=ta_outputs_json,
        memos_json=memos_json,
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


# ---- GET /api/missions ----------------------------------------------------

def test_list_missions_empty(client):
    r = client.get("/api/missions")
    assert r.status_code == 200
    body = r.json()
    assert body["missions"] == []
    assert body["aggregate"] == {
        "invested": 0.0, "current_value": 0.0, "pnl_pct": None,
        "cost": 0.0, "unpriced_count": 0,
    }


def test_list_missions_with_done_mission(client, session):
    _insert_done_mission(
        session, statement="x " * 12,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
    )
    session.commit()
    with patch.object(prices, "get_current_prices",
                      return_value={"NRG": Decimal("110.00")}):
        r = client.get("/api/missions")
    assert r.status_code == 200
    body = r.json()
    assert len(body["missions"]) == 1
    item = body["missions"][0]
    assert item["status"] == "done"
    assert item["position_count"] == 1
    assert item["pnl_pct"] == pytest.approx(10.0)
    assert item["cost_usd"] == 12.5
    # Aggregate: $20k invested, $22k current, +10%
    agg = body["aggregate"]
    assert agg["invested"] == pytest.approx(20000.0)
    assert agg["current_value"] == pytest.approx(22000.0)
    assert agg["pnl_pct"] == pytest.approx(10.0)
    assert agg["cost"] == 12.5
    assert agg["unpriced_count"] == 0


# ---- GET /api/missions/:id ------------------------------------------------

def test_mission_detail_404_invalid_uuid(client):
    assert client.get("/api/missions/not-a-uuid").status_code == 404


def test_mission_detail_404_unknown_id(client):
    assert client.get("/api/missions/00000000-0000-0000-0000-000000000000").status_code == 404


def test_mission_detail_done_returns_full_record(client, session):
    row = _insert_done_mission(
        session, statement="x " * 12,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
        decomposition_json={"sub_themes": [{"id": "s1", "name": "AI Power",
                                            "hypothesis": "data center load",
                                            "confidence": 0.7}]},
        assessments_json={"s1": {
            "candidate_tickers": [
                {"ticker": "NRG", "company_name": "NRG"},
                {"ticker": "VST", "company_name": "Vistra"},
            ],
            "key_findings": ["finding A", "finding B"],
        }},
        shortlist_json={"candidates": [{"ticker": "NRG", "conviction": 5}]},
        ta_outputs_json={"NRG": {
            "ticker": "NRG", "rating": "Buy", "market_report": "ok",
        }},
        memos_json={"NRG": {
            "ticker": "NRG", "conviction": 5, "thesis_alignment": "aligned",
            "reconciliation_notes": "TA Buy + thesis intact",
        }},
    )
    session.commit()
    with patch.object(prices, "get_current_prices",
                      return_value={"NRG": Decimal("110.00")}):
        r = client.get(f"/api/missions/{row.id}")
    assert r.status_code == 200
    body = r.json()
    # Top-level shape
    assert body["id"] == str(row.id)
    assert body["status"] == "done"
    assert body["budget_usd"] == 20000.0
    assert body["cost_usd"] == 12.5
    # Stage JSONB passthrough
    assert body["decomposition_json"]["sub_themes"][0]["name"] == "AI Power"
    assert body["memos_json"]["NRG"]["conviction"] == 5
    # Derived: positions
    assert len(body["positions"]) == 1
    pos = body["positions"][0]
    assert pos["ticker"] == "NRG"
    assert pos["pnl_pct"] == pytest.approx(10.0)
    # Derived: stat_strip
    strip = body["stat_strip"]
    assert strip["invested"] == pytest.approx(20000.0)
    assert strip["current_value"] == pytest.approx(22000.0)
    assert strip["pnl_pct"] == pytest.approx(10.0)
    assert strip["position_count"] == 1
    assert strip["unpriced_count"] == 0
    # Derived: chosen_tickers
    assert body["chosen_tickers"] == ["NRG"]


def test_mission_detail_running_omits_derivations(client, session):
    row = Mission(
        statement="x " * 12, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.running, created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(row); session.commit()
    r = client.get(f"/api/missions/{row.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["positions"] == []
    assert body["stat_strip"] is None
    assert body["chosen_tickers"] == []


def test_mission_detail_failed_returns_error_message(client, session):
    row = Mission(
        statement="x " * 12, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.failed, created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        error_message="pipeline blew up",
    )
    session.add(row); session.commit()
    body = client.get(f"/api/missions/{row.id}").json()
    assert body["status"] == "failed"
    assert body["error_message"] == "pipeline blew up"


# ---- Derivations: subtheme_summary, weak_spots ----------------------------

def test_subtheme_summary_joins_decomposition_assessments_portfolio(client, session):
    """The Jinja UI didn't do this join; the new API must."""
    row = _insert_done_mission(
        session, statement="x " * 12,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
        decomposition_json={"sub_themes": [
            {"id": "s1", "name": "Theme A", "hypothesis": "h1", "confidence": 0.7},
            {"id": "s2", "name": "Theme B", "hypothesis": "h2", "confidence": 0.4},
        ]},
        assessments_json={
            "s1": {"candidate_tickers": [
                {"ticker": "NRG"}, {"ticker": "VST"}, {"ticker": "CEG"},
            ], "key_findings": ["k1", "k2", "k3"]},
            "s2": {"candidate_tickers": [{"ticker": "ETN"}], "key_findings": []},
        },
        portfolio_json={"positions": [{"ticker": "NRG"}],
                        "cash_reserve_pct": 0.0, "rationale": "t"},
    )
    session.commit()
    with patch.object(prices, "get_current_prices",
                      return_value={"NRG": Decimal("100")}):
        body = client.get(f"/api/missions/{row.id}").json()

    summary = {s["id"]: s for s in body["subtheme_summary"]}
    # s1: 3 candidates (NRG, VST, CEG), one Chosen, two passed
    assert summary["s1"]["candidate_count"] == 3
    assert summary["s1"]["chosen_count"] == 1
    assert summary["s1"]["chosen_tickers"] == ["NRG"]
    assert set(summary["s1"]["passed_tickers"]) == {"VST", "CEG"}
    assert summary["s1"]["description"] == "h1"
    assert summary["s1"]["key_findings"] == ["k1", "k2", "k3"]
    # s2: 1 candidate, none chosen
    assert summary["s2"]["candidate_count"] == 1
    assert summary["s2"]["chosen_count"] == 0


def test_weak_spots_flag_fallback_trap_and_losing(client, session):
    row = _insert_done_mission(
        session, statement="x " * 12,
        positions=[
            {"ticker": "AAA", "weight_pct": 0.5, "notional_usd": 10000,
             "entry_price": 100, "rationale": "t"},
            {"ticker": "BBB", "weight_pct": 0.5, "notional_usd": 10000,
             "entry_price": 100, "rationale": "t"},
        ],
        memos_json={
            # AAA: fallback memo, conviction 5, aligned → only fallback flag
            "AAA": {
                "conviction": 5, "thesis_alignment": "aligned",
                "sub_agent_audit": {"memo_writer_fallback": True, "reason": "x"},
            },
            # BBB: conviction 3 with divergence → momentum trap
            "BBB": {
                "conviction": 3, "thesis_alignment": "fully_diverged",
            },
        },
    )
    session.commit()
    # AAA flat, BBB down 20%
    with patch.object(prices, "get_current_prices",
                      return_value={"AAA": Decimal("100"), "BBB": Decimal("80")}):
        body = client.get(f"/api/missions/{row.id}").json()
    spots = {w["ticker"]: w for w in body["weak_spots"]}
    assert spots["AAA"]["is_fallback_memo"] is True
    assert spots["AAA"]["is_momentum_trap"] is False
    assert spots["AAA"]["is_losing"] is False
    assert spots["BBB"]["is_fallback_memo"] is False
    assert spots["BBB"]["is_momentum_trap"] is True
    assert spots["BBB"]["is_losing"] is True
    assert spots["BBB"]["current_pnl_pct"] == pytest.approx(-20.0)


def test_stat_strip_counts_unpriced_positions(client, session):
    """Position with NULL entry_price should land in unpriced_count, not in invested."""
    row = _insert_done_mission(
        session, statement="x " * 12,
        positions=[
            {"ticker": "AAA", "weight_pct": 0.5, "notional_usd": 10000,
             "entry_price": 100, "rationale": "t"},
            {"ticker": "BBB", "weight_pct": 0.5, "notional_usd": 10000,
             # use 0 entry to exercise the divisor guard; current None below also unpriced
             "entry_price": 100, "rationale": "t"},
        ],
    )
    session.commit()
    with patch.object(prices, "get_current_prices",
                      return_value={"AAA": Decimal("110"), "BBB": None}):
        body = client.get(f"/api/missions/{row.id}").json()
    strip = body["stat_strip"]
    assert strip["position_count"] == 2
    assert strip["unpriced_count"] == 1
    assert strip["invested"] == pytest.approx(10000.0)  # only AAA contributes
    assert strip["pnl_pct"] == pytest.approx(10.0)


# ---- POST /api/missions ---------------------------------------------------

def test_post_missions_creates_and_redirects_to_detail_id(client, session):
    from tacapes.dashboard import runners

    payload = {
        "statement": "Buy nuclear names benefiting from AI/data center demand " * 2,
        "budget_usd": 20000,
        "max_positions": 2,
        "max_position_pct": 0.4,
        "horizon_months": 12,
        "sectors_excluded": [],
        "allow_shorts": True,
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
        r = client.post("/api/missions", json=payload)
    assert r.status_code == 201
    mission_id = r.json()["id"]

    with session_scope() as s:
        from tacapes.dashboard.db.models import Mission
        rows = s.query(Mission).all()
        assert len(rows) == 1
        assert str(rows[0].id) == mission_id
        assert rows[0].allow_shorts is True
        assert rows[0].status == MissionStatus.done


def test_post_missions_rejects_short_statement(client):
    r = client.post("/api/missions", json={
        "statement": "too short",
        "budget_usd": 20000, "max_positions": 2, "max_position_pct": 0.4,
        "horizon_months": 12,
    })
    # Pydantic min_length=20 should kick in before the inner validator.
    assert r.status_code in (400, 422)


# ---- DELETE /api/missions/:id --------------------------------------------

def test_delete_mission_returns_204(client, session, tmp_path, monkeypatch):
    from tacapes import config
    monkeypatch.setattr(config, "tacapes_home", lambda: tmp_path)

    row = _insert_done_mission(
        session, statement="x " * 12,
        positions=[{"ticker": "NRG", "weight_pct": 1.0, "notional_usd": 20000,
                    "entry_price": 100, "rationale": "t"}],
    )
    session.commit()
    mission_id = row.id
    (tmp_path / "portfolios" / str(mission_id)).mkdir(parents=True)

    r = client.delete(f"/api/missions/{mission_id}")
    assert r.status_code == 204
    with session_scope() as s:
        assert s.get(Mission, mission_id) is None


def test_delete_running_mission_returns_409(client, session):
    row = Mission(
        statement="x " * 12, budget_usd=Decimal("20000"),
        max_positions=2, max_position_pct=Decimal("0.4"),
        horizon_months=12, sectors_excluded=[], allow_shorts=False,
        status=MissionStatus.running, created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(row); session.commit()
    r = client.delete(f"/api/missions/{row.id}")
    assert r.status_code == 409


# ---- GET /api/missions/:id/status ----------------------------------------

def test_status_endpoint_returns_status_for_each_state(client, session):
    states = [
        (MissionStatus.queued, None, None, None),
        (MissionStatus.running, datetime.now(UTC), None, None),
        (MissionStatus.done, datetime.now(UTC), datetime.now(UTC), None),
        (MissionStatus.failed, datetime.now(UTC), datetime.now(UTC), "boom"),
    ]
    for status, started, completed, err in states:
        row = Mission(
            statement="x " * 12, budget_usd=Decimal("20000"),
            max_positions=2, max_position_pct=Decimal("0.4"),
            horizon_months=12, sectors_excluded=[], allow_shorts=False,
            status=status, created_at=datetime.now(UTC),
            started_at=started, completed_at=completed, error_message=err,
        )
        session.add(row)
    session.commit()

    rows = session.query(Mission).all()
    for row in rows:
        body = client.get(f"/api/missions/{row.id}/status").json()
        assert body["status"] == row.status.value
        if row.status == MissionStatus.failed:
            assert body["error_message"] == "boom"
        else:
            assert body["error_message"] is None


# ---- POST /api/prices/refresh --------------------------------------------

def test_prices_refresh_invalidates_cache(client, session):
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("100"),
        fetched_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post("/api/prices/refresh")
    assert r.status_code == 204
    with session_scope() as s:
        assert s.get(PriceQuote, "NRG") is None


def test_mission_detail_survives_malformed_jsonb_shapes(client, session):
    """Partial-state missions surface JSONB columns shaped like lists (or
    other non-dicts) where the schema expects a dict. The API used to 500
    via Pydantic validation; it now coerces non-dict values to None and
    keeps serving the mission. Surfaced by mission 2c2adfae on 2026-06-01,
    which had `ta_outputs_json = []` and `memos_json = NULL`.
    """
    row = _insert_done_mission(
        session,
        statement="Mission with malformed stage outputs " * 2,
        positions=[],
        decomposition_json={"sub_themes": [{"id": "s1", "name": "Theme"}]},
        # The two shapes worth pinning: empty list and an oddly-shaped value.
        ta_outputs_json=[],            # what the bad row in production had
        memos_json=["unexpected"],     # broader resilience
        # Dict-shaped data still flows through normally.
        shortlist_json={"candidates": [{"ticker": "AAA"}]},
        portfolio_json={"positions": [{"ticker": "AAA"}], "cash_reserve_pct": 0.05},
    )
    session.commit()
    with patch.object(prices, "get_current_prices", return_value={}):
        r = client.get(f"/api/missions/{row.id}")
    assert r.status_code == 200
    body = r.json()
    # Non-dict JSONB fields land as null on the wire.
    assert body["ta_outputs_json"] is None
    assert body["memos_json"] is None
    # Dict-shaped fields pass through unchanged.
    assert body["decomposition_json"]["sub_themes"][0]["id"] == "s1"
    assert body["shortlist_json"]["candidates"][0]["ticker"] == "AAA"
    # Derived fields don't crash on the bad shapes either.
    assert body["weak_spots"] == []
    assert isinstance(body["subtheme_summary"], list)
    assert body["chosen_tickers"] == ["AAA"]
