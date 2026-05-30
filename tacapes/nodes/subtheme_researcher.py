"""M3: ThesisDecomposition.sub_themes → SubThemeAssessment[] via ReAct loop.

Sequential loop over sub-themes. The terminal structured-response call in
each ReAct loop carries the full accumulated tool-result context (~15-20k
tokens); parallel fan-out blows past Anthropic's input-tokens-per-minute
caps. Sequential keeps one fat request in flight at a time.

Prints per-sub-theme progress with elapsed time.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from langgraph.prebuilt import create_react_agent

from ..prompts import load_prompt
from ..schemas import SubTheme, SubThemeAssessment, ThesisDecomposition
from ..tools import fetch_news, web_search
from ..ui import console, working

# v1's SUBTHEME_MAX_ITERS = 8. In LangGraph each tool round is ~2 graph
# steps (model call + tool node), plus a final structured-response step.
# 16 gives the model 7-8 tool turns before hitting the cap.
_RECURSION_LIMIT = 16


def _research_one(agent: Any, sub_theme: SubTheme) -> SubThemeAssessment:
    now_iso = datetime.now(UTC).isoformat()
    user_msg = (
        f"Now: {now_iso}\n\n"
        f"SubTheme:\n{sub_theme.model_dump_json(indent=2)}"
    )
    result = agent.invoke(
        {"messages": [("user", user_msg)]},
        {"recursion_limit": _RECURSION_LIMIT},
    )
    response: SubThemeAssessment = result["structured_response"]

    # Force spine alignment — the LLM may echo back ids verbatim, but we own
    # them here.
    fixed_cands = [
        c.model_copy(update={
            "mission_id": sub_theme.mission_id,
            "sub_theme_ids": c.sub_theme_ids or [sub_theme.id],
        })
        for c in response.candidate_tickers
    ]
    return response.model_copy(update={
        "mission_id": sub_theme.mission_id,
        "sub_theme_id": sub_theme.id,
        "candidate_tickers": fixed_cands,
    })


def subtheme_researcher(
    state: dict,
    *,
    llm: Any | None = None,
) -> dict:
    """Loop sequentially over ThesisDecomposition.sub_themes."""
    decomposition: ThesisDecomposition = state["decomposition"]
    if llm is None:
        # Haiku for the ReAct loop: highest Tier 1 input-tokens/min cap of
        # any Claude model, and capable enough for "search → summarize →
        # propose tickers" research.
        from ..llm import HAIKU_MODEL, get_llm
        llm = get_llm(HAIKU_MODEL)

    agent = create_react_agent(
        llm,
        tools=[web_search, fetch_news],
        prompt=load_prompt("subtheme_researcher"),
        response_format=SubThemeAssessment,
    )

    n = len(decomposition.sub_themes)
    assessments: list[SubThemeAssessment] = []
    for i, st in enumerate(decomposition.sub_themes, 1):
        t0 = time.monotonic()
        with working(f"[{i}/{n}] researching [bold]{st.id}[/] · {st.name}"):
            a = _research_one(agent, st)
        elapsed = time.monotonic() - t0
        console.print(
            f"  [ok]✓[/] [{i}/{n}] [bold]{st.id}[/]  "
            f"·  [bold]{len(a.candidate_tickers)}[/] candidates  "
            f"·  confidence [bold]{a.revised_confidence:.2f}[/]  "
            f"[muted]({elapsed:.0f}s)[/]"
        )
        assessments.append(a)
    return {"assessments": assessments}
