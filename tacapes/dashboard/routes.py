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
            current: dict = {}
            pnl_per_position: dict = {}
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
            chosen: set[str] = set()
            if m.portfolio_json:
                chosen = {
                    p["ticker"]
                    for p in m.portfolio_json.get("positions", [])
                    if "ticker" in p
                }

        return templates.TemplateResponse(request, "mission_detail.html", {
            "m": m,
            "current": current,
            "pnl_per_position": pnl_per_position,
            "chosen": chosen,
        })

    @app.post("/prices/refresh")
    def prices_refresh() -> Any:
        from fastapi.responses import RedirectResponse
        with session_scope() as session:
            prices.invalidate_price_cache(session)
        return RedirectResponse("/", status_code=303)
