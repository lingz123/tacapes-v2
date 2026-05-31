"""
TradingAgentsOutput: raw-ish capture of TradingAgents.propagate() per ticker.

We extract the strings we know about from TA's `final_state` plus the
processed signal. Phase 3 memo_writer consumes this and produces an
`InvestmentMemo` whose drivers/risks/catalysts/thesis_breakers are
synthesized with an LLM call from these prose fields.

We carry the full `PortfolioRating` (5-tier) — the broader granularity
(Buy/Overweight/Hold/Underweight/Sell) maps cleanly to our 1-5 conviction.
"""
from __future__ import annotations

from typing import Literal


from .common import Strict


PortfolioRating = Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]


class TradingAgentsOutput(Strict):
    ticker: str
    mission_id: str
    subtheme_id: str | None = None
    trade_date: str  # ISO date string
    rating: PortfolioRating
    full_decision_markdown: str  # rendered PortfolioDecision (PM's full output)
    market_report: str | None = None
    sentiment_report: str | None = None
    news_report: str | None = None
    fundamentals_report: str | None = None
    investment_plan: str | None = None         # Research Manager's plan
    trader_investment_plan: str | None = None  # Trader's transaction proposal
    risk_debate_judge_decision: str | None = None  # PM's risk-judge wrapup
    price_target: float | None = None
    time_horizon: str | None = None
    suggested_position_pct: float | None = None  # parsed from PM if available
