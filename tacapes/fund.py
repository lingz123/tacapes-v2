"""
The Fund — the only module that reads/writes ~/.tacapes/fund.json.

`build_fund_from_run` is the cold-start path (design §6): it turns a finished
mission run into the first fund with zero extra LLM work. The v2.0 pipeline
already evaluates `max_positions × 3` shortlisted tickers through ta_runner +
memo_writer — the names the constructor *didn't* pick already have full memos.
So the constructor's chosen names become `held` Holdings and the passed-over
names become `watch` Holdings, both monitorable and refreshable from day one.

`refresh_holding` is the Phase 2 write-back: a refresh re-evaluates one ticker
and updates the matching Holding's health signals (conviction, alignment, …).
A refresh reports — it never trades — so weights and notional are untouched.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import tacapes_home
from .schemas import (
    Fund,
    Holding,
    InvestmentMemo,
    Mission,
    MissionRef,
    PortfolioAllocation,
    PortfolioRating,
    TradingAgentsOutput,
)


# ---------- paths ----------

def fund_path() -> Path:
    return tacapes_home() / "fund.json"


def fund_exists() -> bool:
    return fund_path().exists()


def _memo_ref(mission_id: str, ticker: str) -> str:
    """Path to a ticker's latest memo, relative to ~/.tacapes/ — stored on
    the Holding as lineage. Relative so it survives a state-dir move."""
    return f"portfolios/{mission_id}/memos/{ticker.upper()}.json"


# ---------- load / save ----------

def load_fund() -> Fund:
    return Fund.model_validate_json(fund_path().read_text(encoding="utf-8"))


def save_fund(fund: Fund) -> Path:
    """Persist the fund, stamping `updated_at`. Returns the path written."""
    fund.updated_at = datetime.now(UTC)
    path = fund_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fund.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------- holding accessors ----------

def get_holding(fund: Fund, ticker: str) -> Holding | None:
    t = ticker.upper()
    for h in fund.holdings:
        if h.ticker.upper() == t:
            return h
    return None


def upsert_holding(fund: Fund, holding: Holding) -> None:
    """Replace the holding with the same ticker in place, or append it."""
    t = holding.ticker.upper()
    for i, h in enumerate(fund.holdings):
        if h.ticker.upper() == t:
            fund.holdings[i] = holding
            return
    fund.holdings.append(holding)


def held(fund: Fund) -> list[Holding]:
    return [h for h in fund.holdings if h.status == "held"]


def watchlist(fund: Fund) -> list[Holding]:
    return [h for h in fund.holdings if h.status == "watch"]


# ---------- cold-start creation ----------

def build_fund_from_run(
    *,
    mission: Mission,
    portfolio: PortfolioAllocation,
    ta_memos: list[InvestmentMemo],
    ta_outputs: list[TradingAgentsOutput],
) -> Fund:
    """Cold-start: turn a finished mission run into the first Fund.

    Held = the constructor's chosen positions. Watch = every memo'd ticker the
    constructor did not pick — the passed-over names, which already have full
    memos. NAV is fixed at the mission budget; cash is at cost.
    """
    now = datetime.now(UTC)
    memos_by_ticker = {m.ticker.upper(): m for m in ta_memos}
    rating_by_ticker = {o.ticker.upper(): o.rating for o in ta_outputs}
    portfolio_tickers = {p.ticker.upper() for p in portfolio.positions}

    holdings: list[Holding] = []

    # Held — one Holding per final position.
    for p in portfolio.positions:
        tk = p.ticker.upper()
        memo = memos_by_ticker[tk]
        holdings.append(Holding(
            ticker=tk,
            status="held",
            weight_pct=p.weight_pct,
            notional_usd=p.notional_usd,
            conviction=memo.conviction,
            ta_rating=rating_by_ticker[tk],
            thesis_alignment=memo.thesis_alignment,
            thesis_one_liner=memo.thesis_one_liner,
            note=p.rationale,
            source_mission_id=mission.id,
            subtheme_id=memo.subtheme_id,
            memo_ref=_memo_ref(mission.id, tk),
            added_at=now,
            last_refreshed=memo.last_refreshed,
        ))

    # Watch — every memo'd ticker the constructor passed over.
    for memo in ta_memos:
        tk = memo.ticker.upper()
        if tk in portfolio_tickers:
            continue
        holdings.append(Holding(
            ticker=tk,
            status="watch",
            conviction=memo.conviction,
            ta_rating=rating_by_ticker[tk],
            thesis_alignment=memo.thesis_alignment,
            thesis_one_liner=memo.thesis_one_liner,
            note=memo.reconciliation_notes,  # why it lost out
            source_mission_id=mission.id,
            subtheme_id=memo.subtheme_id,
            memo_ref=_memo_ref(mission.id, tk),
            added_at=now,
            last_refreshed=memo.last_refreshed,
        ))

    return Fund(
        nav_usd=mission.budget_usd,
        cash_usd=mission.budget_usd * portfolio.cash_reserve_pct,
        holdings=holdings,
        mission_log=[MissionRef(
            mission_id=mission.id,
            statement=mission.statement,
            mode=portfolio.mode,
            applied_at=now,
        )],
        created_at=now,
        updated_at=now,
    )


# ---------- refresh write-back ----------

def refresh_holding(
    fund: Fund,
    *,
    ticker: str,
    memo: InvestmentMemo,
    ta_rating: PortfolioRating,
) -> Holding:
    """Update a held/watch Holding's health signals from a fresh memo.

    Weights and notional are untouched — a refresh reports, it does not trade
    (design §5.1). Returns the updated Holding. Raises KeyError if the ticker
    is not in the fund.
    """
    old = get_holding(fund, ticker)
    if old is None:
        raise KeyError(f"no holding for {ticker!r} in fund")
    updated = old.model_copy(update={
        "conviction": memo.conviction,
        "ta_rating": ta_rating,
        "thesis_alignment": memo.thesis_alignment,
        "thesis_one_liner": memo.thesis_one_liner,
        "last_refreshed": datetime.now(UTC),
    })
    upsert_holding(fund, updated)
    return updated
