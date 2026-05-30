"""
ta_runner: per-ticker TradingAgents wrapper.

Two callables exposed:
  - `ta_runner` — calls real TradingAgentsGraph.propagate(ticker, today).
  - `mock_ta_runner` — returns canned TradingAgentsOutput[], for tests.

Both loop over `state["shortlist"].candidates` sequentially. Was Send fan-out;
serialized because TradingAgents' internal multi-analyst calls × N parallel
tickers burst past Anthropic's input-tokens-per-minute caps. One TA debate
at a time = one stream of internal calls = headroom.
"""
from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any, cast

from ..schemas import CandidateTicker, Shortlist, TradingAgentsOutput
from ..schemas.ta_output import PortfolioRating
from ..ui import console, working


_RATING_LABEL_RE = re.compile(
    r"^\s*(?:[*_~`]+\s*)*Rating(?:[*_~`]+)?\s*[:\-]\s*[*_~`]*\s*"
    r"(Buy|Overweight|Hold|Underweight|Sell)\s*[*_~`]*\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:of)?\s*(?:portfolio|the\s+portfolio)?")


def _extract_rating(decision_text: str) -> PortfolioRating:
    m = _RATING_LABEL_RE.search(decision_text)
    if m:
        return cast(PortfolioRating, m.group(1).capitalize())
    # Fallback: first 5-tier word found anywhere.
    for word in decision_text.split():
        clean = word.strip("*:.,").capitalize()
        if clean in {"Buy", "Overweight", "Hold", "Underweight", "Sell"}:
            return cast(PortfolioRating, clean)
    return "Hold"


def _extract_position_pct(text: str | None) -> float | None:
    if not text:
        return None
    m = _PCT_RE.search(text)
    if not m:
        return None
    pct = float(m.group(1))
    if pct > 1.0:
        pct = pct / 100.0
    return min(max(pct, 0.0), 1.0)


def _extract_price_target(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"Price Target[*_:\s]+\$?([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_horizon(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"Time Horizon[*_:\s]+([^\n.]+)", text, re.IGNORECASE)
    return m.group(1).strip().rstrip("*").strip() if m else None


def _build_output(
    *,
    ticker: str,
    mission_id: str,
    subtheme_id: str | None,
    trade_date: str,
    final_state: dict[str, Any],
) -> TradingAgentsOutput:
    decision_md = str(final_state.get("final_trade_decision", ""))
    return TradingAgentsOutput(
        ticker=ticker,
        mission_id=mission_id,
        subtheme_id=subtheme_id,
        trade_date=trade_date,
        rating=_extract_rating(decision_md),
        full_decision_markdown=decision_md,
        market_report=final_state.get("market_report"),
        sentiment_report=final_state.get("sentiment_report"),
        news_report=final_state.get("news_report"),
        fundamentals_report=final_state.get("fundamentals_report"),
        investment_plan=final_state.get("investment_plan"),
        trader_investment_plan=final_state.get("trader_investment_plan"),
        risk_debate_judge_decision=(
            final_state.get("risk_debate_state", {}).get("judge_decision")
            if isinstance(final_state.get("risk_debate_state"), dict)
            else None
        ),
        price_target=_extract_price_target(decision_md),
        time_horizon=_extract_horizon(decision_md),
        suggested_position_pct=_extract_position_pct(decision_md),
    )


def propagate_one(cand: CandidateTicker, mission_id: str) -> TradingAgentsOutput:
    """Run one TradingAgents debate for a single candidate. Public primitive —
    reused by `tacapes/refresh.py` to re-evaluate a held/watch ticker without
    re-running the M2/M3/M4 stages."""
    from ..config import make_ta_config  # noqa: PLC0415
    from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: PLC0415

    cfg = make_ta_config(mission_id=mission_id)
    ta = TradingAgentsGraph(debug=False, config=cfg)

    trade_date = datetime.now(UTC).date().isoformat()
    final_state, _processed = ta.propagate(cand.ticker, trade_date)

    return _build_output(
        ticker=cand.ticker,
        mission_id=mission_id,
        subtheme_id=cand.sub_theme_ids[0] if cand.sub_theme_ids else None,
        trade_date=trade_date,
        final_state=final_state,
    )


def ta_runner(state: dict) -> dict:
    """Real TradingAgents per ticker, looped sequentially over the shortlist.

    Requires ANTHROPIC_API_KEY in env. Each `propagate_one` call kicks off
    a full multi-analyst debate inside TradingAgents (sequential within a
    debate), so the total here is sum-of-debates not max-of-debates.

    Prints per-ticker progress with elapsed time — this is the slowest stage
    so live output is essential.
    """
    sl: Shortlist = state["shortlist"]
    n = len(sl.candidates)
    outputs: list[TradingAgentsOutput] = []
    for i, c in enumerate(sl.candidates, 1):
        t0 = time.monotonic()
        try:
            with working(
                f"[{i}/{n}] [bold]{c.ticker}[/] · TradingAgents multi-analyst debate",
            ):
                out = propagate_one(c, sl.mission_id)
            elapsed = time.monotonic() - t0
            pt = f"${out.price_target:,.2f}" if out.price_target is not None else "—"
            console.print(
                f"  [ok]✓[/] [{i}/{n}] [bold]{c.ticker}[/]  →  "
                f"[rating.{out.rating}]{out.rating}[/]  ·  "
                f"target {pt}  [muted]({elapsed:.0f}s)[/]"
            )
            outputs.append(out)
        except Exception as e:
            # Don't kill the whole run for one ticker's failure — log and skip.
            elapsed = time.monotonic() - t0
            console.print(
                f"  [err]✗[/] [{i}/{n}] [bold]{c.ticker}[/] failed after "
                f"{elapsed:.0f}s  [muted]{type(e).__name__}: {str(e)[:120]}[/]"
            )
    return {"ta_outputs": outputs}


def _mock_output(cand: CandidateTicker, mission_id: str) -> TradingAgentsOutput:
    return TradingAgentsOutput(
        ticker=cand.ticker,
        mission_id=mission_id,
        subtheme_id=cand.sub_theme_ids[0] if cand.sub_theme_ids else None,
        trade_date=datetime.now(UTC).date().isoformat(),
        rating="Buy",
        full_decision_markdown=(
            f"**Rating**: Buy\n\n"
            f"**Executive Summary**: phase-2 stub; size at 5% of portfolio.\n\n"
            f"**Investment Thesis**: stubbed thesis for {cand.ticker}.\n\n"
            f"**Price Target**: 100\n\n"
            f"**Time Horizon**: 3-6 months"
        ),
        market_report=None,
        sentiment_report=None,
        news_report=None,
        fundamentals_report=None,
        investment_plan=None,
        trader_investment_plan=None,
        risk_debate_judge_decision=None,
        price_target=100.0,
        time_horizon="3-6 months",
        suggested_position_pct=0.05,
    )


def mock_ta_runner(state: dict) -> dict:
    """Test stand-in: builds one canned TradingAgentsOutput per shortlist candidate."""
    sl: Shortlist = state["shortlist"]
    outputs = [_mock_output(c, sl.mission_id) for c in sl.candidates]
    return {"ta_outputs": outputs}
