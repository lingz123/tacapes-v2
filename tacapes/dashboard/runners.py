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
                        "is_short": bool(p.get("is_short", False)),
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

        except Exception as e:  # noqa: BLE001 — recorded, not re-raised
            log.exception("mission %s failed", mission_id)
            with session_scope() as s:
                mark_failed(s, mission_id, f"{type(e).__name__}: {e}")
            return f"mission {mission_id} failed"

    return fn
