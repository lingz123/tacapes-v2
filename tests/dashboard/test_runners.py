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
