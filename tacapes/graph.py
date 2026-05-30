"""
LangGraph DAG for tacapes-v2.

  START → thesis_decomposer
        → subtheme_researcher       (sequential loop over sub-themes)
        → shortlist
        → ta_runner                 (sequential loop over candidates)
        → memo_writer               (sequential loop over ta_outputs)
        → portfolio_constructor
        → persist
        → END

Originally three Send-based fan-outs (subtheme_researcher, ta_runner,
memo_writer) ran in parallel. Each parallel fan-out fought Anthropic's
input-tokens-per-minute cap: per-branch terminal calls carry ~10-20k tokens
of accumulated context, and N branches doing that simultaneously burst
through any tier's ITPM ceiling. Sequential loops keep only one fat
request in flight at a time, which is what the rate limit fundamentally
allows. Trades wall-clock for reliability.

Each agentic node accepts an optional override via `build_graph` so tests
run the topology without making real LLM calls.
"""
from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from .nodes.memo_writer import memo_writer as memo_writer_node
from .nodes.persist import persist as persist_node
from .nodes.portfolio_constructor import portfolio_constructor as portfolio_constructor_node
from .nodes.shortlist import shortlist as shortlist_node
from .nodes.subtheme_researcher import subtheme_researcher as subtheme_researcher_node
from .nodes.ta_runner import ta_runner as ta_runner_node
from .nodes.thesis_decomposer import thesis_decomposer as thesis_decomposer_node
from .state import GraphState


def build_graph(
    *,
    thesis_decomposer: Callable | None = None,
    subtheme_researcher: Callable | None = None,
    shortlist: Callable | None = None,
    ta_runner: Callable | None = None,
    memo_writer: Callable | None = None,
    portfolio_constructor: Callable | None = None,
    persist: Callable | None = None,
) -> Any:
    g = StateGraph(GraphState)

    g.add_node("thesis_decomposer", thesis_decomposer or thesis_decomposer_node)
    g.add_node("subtheme_researcher", subtheme_researcher or subtheme_researcher_node)
    g.add_node("shortlist", shortlist or shortlist_node)
    g.add_node("ta_runner", ta_runner or ta_runner_node)
    g.add_node("memo_writer", memo_writer or memo_writer_node)
    g.add_node("portfolio_constructor", portfolio_constructor or portfolio_constructor_node)
    g.add_node("persist", persist or persist_node)

    g.add_edge(START, "thesis_decomposer")
    g.add_edge("thesis_decomposer", "subtheme_researcher")
    g.add_edge("subtheme_researcher", "shortlist")
    g.add_edge("shortlist", "ta_runner")
    g.add_edge("ta_runner", "memo_writer")
    g.add_edge("memo_writer", "portfolio_constructor")
    g.add_edge("portfolio_constructor", "persist")
    g.add_edge("persist", END)

    return g.compile()
