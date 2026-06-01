"""JSON API route handlers.

Conventions:
- All routes return Pydantic response models or 204.
- All Decimal columns convert to `float` at the wire boundary.
- All UUID columns convert to `str`.
- Missing/null JSONB blobs serialize as `None`, not `{}`.
- Derivations (`stat_strip`, `subtheme_summary`, `weak_spots`) are computed
  here so the frontend doesn't re-implement portfolio math.

Defensive throughout: backfilled missions may lack fields we now expect
(e.g. some pre-v2 memos have no `sub_agent_audit`). Use `.get()` and
None-checks; raise no errors over absent data.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .. import prices
from ..db import session_scope
from ..db.models import Mission, MissionStatus
from ..db.repo import (
    delete_mission as repo_delete_mission,
    get_mission_with_positions,
    insert_mission,
    list_missions,
)
from .schemas import (
    AggregateStats,
    CreateMissionRequest,
    CreateMissionResponse,
    MissionDetail,
    MissionListItem,
    MissionListResponse,
    MissionStatusResponse,
    PositionPnl,
    StatStrip,
    SubthemeSummary,
    WeakSpot,
)


def _to_float(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    """Coerce a JSONB column to dict-or-None for the wire schema.

    The `*_json` columns are typed `dict[str, Any] | None` on the response
    model, but the underlying JSONB can hold any JSON shape. Partial-state
    missions in particular have surfaced `ta_outputs_json = []` (empty list)
    where the pipeline crashed between writing the stage container and
    populating it. Returning None for any non-dict value keeps the API
    available; the React side already renders "no X recorded" gracefully
    for null. We deliberately don't rewrite the DB row — keep the bad
    shape on disk so the upstream bug stays diagnosable.
    """
    return value if isinstance(value, dict) else None


def _per_position_pnl(
    positions: list[Any], current_prices: dict[str, Decimal]
) -> list[PositionPnl]:
    out: list[PositionPnl] = []
    for p in positions:
        cur = current_prices.get(p.ticker)
        pnl_pct: float | None = None
        if p.entry_price and cur and p.entry_price > 0:
            pnl_pct = float((cur - p.entry_price) / p.entry_price * 100)
        out.append(PositionPnl(
            ticker=p.ticker,
            weight_pct=float(p.weight_pct),
            notional_usd=float(p.notional_usd),
            rationale=p.rationale,
            entry_price=_to_float(p.entry_price),
            entry_price_date=p.entry_price_date.isoformat() if p.entry_price_date else None,
            current_price=_to_float(cur),
            pnl_pct=pnl_pct,
        ))
    return out


def _stat_strip(
    mission: Mission, positions: list[PositionPnl]
) -> StatStrip | None:
    """For done missions, snapshot the portfolio outcome."""
    if mission.status != MissionStatus.done or not positions:
        return None
    invested = Decimal("0")
    current = Decimal("0")
    unpriced = 0
    for p in positions:
        if p.entry_price is None or p.current_price is None or p.entry_price == 0:
            unpriced += 1
            continue
        shares = Decimal(str(p.notional_usd)) / Decimal(str(p.entry_price))
        invested += Decimal(str(p.notional_usd))
        current += shares * Decimal(str(p.current_price))
    pnl_pct: float | None = None
    pnl_usd: float | None = None
    if invested > 0:
        pnl_pct = float((current - invested) / invested) * 100
        pnl_usd = float(current - invested)
    cash_reserve_pct = 0.0
    portfolio = _dict_or_none(mission.portfolio_json) or {}
    if portfolio:
        cash_reserve_pct = float(portfolio.get("cash_reserve_pct") or 0.0)
    return StatStrip(
        invested=float(invested),
        current_value=float(current),
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        unpriced_count=unpriced,
        position_count=len(positions),
        cash_reserve_pct=cash_reserve_pct,
    )


def _subtheme_summary(mission: Mission, chosen: set[str]) -> list[SubthemeSummary]:
    """Join decomposition × assessments × portfolio.

    The Jinja UI rendered sub-theses as bare names. This is the join the
    spec called for: per-subtheme name + hypothesis + candidate count +
    chosen ratio + key findings preview.
    """
    decomp = _dict_or_none(mission.decomposition_json) or {}
    assessments = _dict_or_none(mission.assessments_json) or {}
    out: list[SubthemeSummary] = []
    for st in decomp.get("sub_themes") or []:
        sid = st.get("id") or st.get("name") or "(unknown)"
        assessment = assessments.get(sid) or {}
        candidates = assessment.get("candidate_tickers") or []
        candidate_tickers = [c.get("ticker") for c in candidates if c.get("ticker")]
        chosen_tickers = [t for t in candidate_tickers if t in chosen]
        passed_tickers = [t for t in candidate_tickers if t not in chosen]
        out.append(SubthemeSummary(
            id=sid,
            name=st.get("name") or sid,
            description=st.get("hypothesis") or st.get("description"),
            confidence=st.get("confidence"),
            candidate_count=len(candidate_tickers),
            chosen_count=len(chosen_tickers),
            chosen_tickers=chosen_tickers,
            passed_tickers=passed_tickers,
            key_findings=list(assessment.get("key_findings") or [])[:5],
        ))
    return out


def _weak_spots(mission: Mission, positions: list[PositionPnl]) -> list[WeakSpot]:
    """Per-memo flags surfaced as icons in the React UI.

    - fallback memo: memo.sub_agent_audit.memo_writer_fallback truthy
    - momentum trap: conviction == 3 AND thesis_alignment != 'aligned'
      (the matrix collapses to 3 when TA and thesis disagree strongly)
    - losing: current pnl_pct < 0 for this ticker's position
    """
    out: list[WeakSpot] = []
    memos = _dict_or_none(mission.memos_json) or {}
    pnl_by_ticker = {p.ticker: p.pnl_pct for p in positions}
    for ticker, memo in memos.items():
        if not isinstance(memo, dict):
            continue
        audit = memo.get("sub_agent_audit") or {}
        is_fallback = bool(audit.get("memo_writer_fallback"))
        conviction = memo.get("conviction")
        alignment = memo.get("thesis_alignment")
        is_trap = conviction == 3 and alignment not in ("aligned", None)
        pnl = pnl_by_ticker.get(ticker)
        is_losing = pnl is not None and pnl < 0
        out.append(WeakSpot(
            ticker=ticker,
            is_fallback_memo=is_fallback,
            is_momentum_trap=is_trap,
            is_losing=is_losing,
            current_pnl_pct=pnl,
        ))
    return out


def _chosen_tickers(mission: Mission) -> set[str]:
    portfolio = _dict_or_none(mission.portfolio_json)
    if not portfolio:
        return set()
    return {
        p["ticker"]
        for p in (portfolio.get("positions") or [])
        if isinstance(p, dict) and "ticker" in p
    }


def _aggregate_stats(rows: list[tuple[Mission, list[PositionPnl]]]) -> AggregateStats:
    """All-time totals across every done mission."""
    invested = Decimal("0")
    current = Decimal("0")
    unpriced = 0
    cost = Decimal("0")
    for mission, positions in rows:
        if mission.cost_usd is not None:
            cost += mission.cost_usd
        if mission.status != MissionStatus.done:
            continue
        for p in positions:
            if p.entry_price is None or p.current_price is None or p.entry_price == 0:
                unpriced += 1
                continue
            shares = Decimal(str(p.notional_usd)) / Decimal(str(p.entry_price))
            invested += Decimal(str(p.notional_usd))
            current += shares * Decimal(str(p.current_price))
    pnl_pct: float | None = None
    if invested > 0:
        pnl_pct = float((current - invested) / invested) * 100
    return AggregateStats(
        invested=float(invested),
        current_value=float(current),
        pnl_pct=pnl_pct,
        cost=float(cost),
        unpriced_count=unpriced,
    )


def _parse_uuid(mission_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(mission_id)
    except ValueError as e:
        raise HTTPException(status_code=404) from e


def register(app: FastAPI) -> None:
    @app.get("/api/missions", response_model=MissionListResponse)
    def get_missions() -> MissionListResponse:
        with session_scope() as session:
            missions = list_missions(session)
            # For done missions, eager-load positions for the P&L cell.
            full_missions: list[Mission] = []
            for m in missions:
                if m.status == MissionStatus.done:
                    loaded = get_mission_with_positions(session, m.id)
                    full_missions.append(loaded if loaded is not None else m)
                else:
                    full_missions.append(m)

            tickers = sorted({
                p.ticker
                for m in full_missions
                if m.status == MissionStatus.done
                for p in m.positions
            })
            current = prices.get_current_prices(session, tickers)

            rows: list[tuple[Mission, list[PositionPnl]]] = []
            items: list[MissionListItem] = []
            for m in full_missions:
                positions = (
                    _per_position_pnl(m.positions, current)
                    if m.status == MissionStatus.done else []
                )
                rows.append((m, positions))

                pnl_pct: float | None = None
                if positions:
                    strip = _stat_strip(m, positions)
                    pnl_pct = strip.pnl_pct if strip is not None else None

                items.append(MissionListItem(
                    id=str(m.id),
                    statement=m.statement,
                    status=m.status.value,
                    created_at=m.created_at,
                    completed_at=m.completed_at,
                    cost_usd=_to_float(m.cost_usd),
                    pnl_pct=pnl_pct,
                    position_count=len(positions),
                ))

            return MissionListResponse(
                missions=items,
                aggregate=_aggregate_stats(rows),
            )

    @app.get("/api/missions/{mission_id}", response_model=MissionDetail)
    def get_mission(mission_id: str) -> MissionDetail:
        mid = _parse_uuid(mission_id)
        with session_scope() as session:
            m = get_mission_with_positions(session, mid)
            if m is None:
                raise HTTPException(status_code=404)

            positions: list[PositionPnl] = []
            chosen: set[str] = set()
            if m.status == MissionStatus.done:
                tickers = sorted({p.ticker for p in m.positions})
                current = prices.get_current_prices(session, tickers)
                positions = _per_position_pnl(m.positions, current)
                chosen = _chosen_tickers(m)

            return MissionDetail(
                id=str(m.id),
                statement=m.statement,
                status=m.status.value,
                budget_usd=float(m.budget_usd),
                max_positions=m.max_positions,
                max_position_pct=float(m.max_position_pct),
                horizon_months=m.horizon_months,
                sectors_excluded=list(m.sectors_excluded),
                allow_shorts=m.allow_shorts,
                created_at=m.created_at,
                started_at=m.started_at,
                completed_at=m.completed_at,
                error_message=m.error_message,
                cost_usd=_to_float(m.cost_usd),
                decomposition_json=_dict_or_none(m.decomposition_json),
                assessments_json=_dict_or_none(m.assessments_json),
                shortlist_json=_dict_or_none(m.shortlist_json),
                ta_outputs_json=_dict_or_none(m.ta_outputs_json),
                memos_json=_dict_or_none(m.memos_json),
                portfolio_json=_dict_or_none(m.portfolio_json),
                positions=positions,
                stat_strip=_stat_strip(m, positions),
                subtheme_summary=_subtheme_summary(m, chosen),
                weak_spots=_weak_spots(m, positions),
                chosen_tickers=sorted(chosen),
            )

    @app.post("/api/missions", response_model=CreateMissionResponse, status_code=201)
    def post_missions(payload: CreateMissionRequest, request: Any = None) -> CreateMissionResponse:
        # Re-validate via the pipeline's own constraints model so the API
        # rejects the same shapes the CLI does.
        from pydantic import ValidationError

        from ...schemas import Mission as PMission, MissionConstraints

        try:
            constraints = MissionConstraints(
                max_position_pct=payload.max_position_pct,
                max_positions=payload.max_positions,
                sectors_excluded=payload.sectors_excluded,
                allow_shorts=payload.allow_shorts,
                time_horizon_months=payload.horizon_months,
            )
            PMission(
                statement=payload.statement,
                budget_usd=payload.budget_usd,
                constraints=constraints,
            )
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        from ..runners import make_mission_job

        with session_scope() as session:
            row = insert_mission(
                session,
                statement=payload.statement,
                budget_usd=Decimal(str(payload.budget_usd)),
                max_positions=payload.max_positions,
                max_position_pct=Decimal(str(payload.max_position_pct)),
                horizon_months=payload.horizon_months,
                sectors_excluded=list(payload.sectors_excluded),
                allow_shorts=payload.allow_shorts,
            )
            session.flush()
            mission_id = row.id

        runner = app.state.job_runner
        runner.submit(
            kind="mission",
            target=payload.statement[:80],
            fn=make_mission_job(mission_id),
        )
        return CreateMissionResponse(id=str(mission_id))

    @app.delete("/api/missions/{mission_id}", status_code=204)
    def delete_mission_endpoint(mission_id: str) -> Response:
        import shutil
        from ...config import tacapes_home

        mid = _parse_uuid(mission_id)
        with session_scope() as session:
            m = session.get(Mission, mid)
            if m is None:
                raise HTTPException(status_code=404)
            if m.status == MissionStatus.running:
                raise HTTPException(status_code=409, detail="cannot delete a running mission")
            repo_delete_mission(session, mid)
        folder = tacapes_home() / "portfolios" / str(mid)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        return Response(status_code=204)

    @app.get("/api/missions/{mission_id}/status", response_model=MissionStatusResponse)
    def get_mission_status(mission_id: str) -> MissionStatusResponse:
        mid = _parse_uuid(mission_id)
        with session_scope() as session:
            m = session.get(Mission, mid)
            if m is None:
                raise HTTPException(status_code=404)
            return MissionStatusResponse(
                status=m.status.value,
                started_at=m.started_at,
                completed_at=m.completed_at,
                error_message=m.error_message,
            )

    @app.post("/api/prices/refresh", status_code=204)
    def refresh_prices() -> Response:
        with session_scope() as session:
            prices.invalidate_price_cache(session)
        return Response(status_code=204)
