"""M4: Mission + assessments → Shortlist.

After the LLM call, applies a deterministic post-filter:
- dedupe by ticker (merge sub_theme_ids on collision)
- drop candidates whose `why_relevant` mentions an excluded sector
- force `mission_id` on the shortlist and every CandidateTicker
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..prompts import load_prompt
from ..schemas import (
    CandidateTicker,
    Mission,
    Shortlist,
    SubThemeAssessment,
)
from ..state import GraphState


class _ShortlistInput(BaseModel):
    mission: Mission
    assessments: list[SubThemeAssessment]
    # Tickers already held in the fund — context for an incremental run so the
    # LLM knows what is already owned (design §5.2). Empty on a cold start.
    held_tickers: list[str] = []


def shortlist(
    state: GraphState,
    *,
    llm: Any | None = None,
) -> dict:
    mission: Mission = state["mission"]
    assessments: list[SubThemeAssessment] = state.get("assessments", [])
    fund = state.get("fund")
    held_tickers = (
        sorted({h.ticker.upper() for h in fund.holdings if h.status == "held"})
        if fund is not None
        else []
    )

    if llm is None:
        from ..llm import DEFAULT_MODEL, get_llm
        llm = get_llm(DEFAULT_MODEL)

    structured = llm.with_structured_output(Shortlist)
    payload = _ShortlistInput(
        mission=mission, assessments=assessments, held_tickers=held_tickers
    )
    response: Shortlist = structured.invoke([
        ("system", load_prompt("shortlist")),
        ("user", payload.model_dump_json(indent=2)),
    ])

    excluded = {s.lower() for s in mission.constraints.sectors_excluded}
    seen: dict[str, CandidateTicker] = {}
    for c in response.candidates:
        if any(s in c.why_relevant.lower() for s in excluded):
            continue
        ticker = c.ticker.upper()
        c = c.model_copy(update={"ticker": ticker, "mission_id": mission.id})
        if ticker in seen:
            existing = seen[ticker]
            merged = sorted({*existing.sub_theme_ids, *c.sub_theme_ids})
            seen[ticker] = existing.model_copy(update={"sub_theme_ids": merged})
        else:
            seen[ticker] = c

    final = Shortlist(
        mission_id=mission.id,
        candidates=list(seen.values()),
        ranking_rationale=response.ranking_rationale,
    )
    return {"shortlist": final}
