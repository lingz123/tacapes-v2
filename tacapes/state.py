"""
LangGraph shared state.

`assessments`, `ta_outputs`, and `ta_memos` use `Annotated[..., add]` so
parallel fan-out branches accumulate results into a list (the standard
LangGraph reducer pattern).

Pipeline:
  mission → decomposition → assessments[] → shortlist
        → ta_outputs[] (raw TradingAgents)
        → ta_memos[]   (memo_writer translates each ta_output)
        → portfolio
"""
from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from .schemas import (
    Fund,
    InvestmentMemo,
    Mission,
    PortfolioAllocation,
    RebalanceProposal,
    Shortlist,
    SubThemeAssessment,
    ThesisDecomposition,
    TradingAgentsOutput,
)


class GraphState(TypedDict, total=False):
    mission: Mission
    # `fund` is an optional INPUT: when present the run is incremental — the
    # constructor emits a `proposal` instead of a cold-start `portfolio`.
    fund: Fund
    decomposition: ThesisDecomposition
    assessments: Annotated[list[SubThemeAssessment], add]
    shortlist: Shortlist
    ta_outputs: Annotated[list[TradingAgentsOutput], add]
    ta_memos: Annotated[list[InvestmentMemo], add]
    portfolio: PortfolioAllocation        # cold-start output
    proposal: RebalanceProposal           # incremental output
