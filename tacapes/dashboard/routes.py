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
