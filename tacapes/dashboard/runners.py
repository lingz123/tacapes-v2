"""
Job bodies for the dashboard's JobRunner.

`make_refresh_job` / `make_thesis_job` build the `fn(progress) -> result_ref`
closures the JobRunner executes on its single worker. They run the real
pipeline (TradingAgents debates, the LangGraph DAG) — minutes long and
metered — which is exactly why they run as background jobs, not inline in
an HTTP handler.
"""
from __future__ import annotations

from typing import Callable

from .jobs import JobFn


def make_refresh_job(ticker: str) -> JobFn:
    """A job that re-evaluates one held/watch holding and writes the refreshed
    conviction/alignment back to the fund."""

    def fn(progress: Callable[[str], None]) -> str:
        from ..fund import get_holding, load_fund, refresh_holding, save_fund
        from ..refresh import refresh_ticker

        progress(f"loading {ticker}")
        fund = load_fund()
        holding = get_holding(fund, ticker)
        if holding is None:
            raise ValueError(f"{ticker} is not in the fund")

        progress(f"{ticker}: TradingAgents debate + memo reconciliation")
        result = refresh_ticker(holding)
        refresh_holding(
            fund, ticker=ticker, memo=result.memo, ta_rating=result.ta_rating
        )
        save_fund(fund)
        return (
            f"{ticker}: conviction {result.prior_conviction}"
            f"→{result.new_conviction}"
        )

    return fn


def make_thesis_job(statement: str, budget: float, max_positions: int) -> JobFn:
    """A job that runs a full thesis: cold start if no fund exists, otherwise
    an incremental run that emits a RebalanceProposal."""

    def fn(progress: Callable[[str], None]) -> str:
        from ..fund import fund_exists, load_fund
        from ..graph import build_graph
        from ..schemas import Mission, MissionConstraints

        mission = Mission(
            statement=statement,
            budget_usd=budget,
            constraints=MissionConstraints(
                max_position_pct=0.4,
                max_positions=max_positions,
                time_horizon_months=12,
            ),
        )
        initial: dict = {"mission": mission}
        if fund_exists():
            initial["fund"] = load_fund()

        final: dict = {}
        for chunk in build_graph().stream(initial, stream_mode="updates"):
            for node_name, update in chunk.items():
                progress(node_name)
                if update:
                    final.update(update)

        if "proposal" in final:
            return f"proposal {final['proposal'].id}"
        if "portfolio" in final:
            return "cold-start fund created"
        return "thesis run finished (no portfolio/proposal)"

    return fn
