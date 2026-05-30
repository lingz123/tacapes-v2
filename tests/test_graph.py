"""
Phase 1 end-to-end test.

Bypasses real LLMs by injecting node overrides that return canned data.
This validates the LangGraph topology + spine propagation, not LLM
behaviour. Real-LLM smoke tests come in Phase 2 (gated on
ANTHROPIC_API_KEY).
"""
from __future__ import annotations

from datetime import UTC, datetime

from tacapes.graph import build_graph
from tacapes.schemas import (
    CandidateTicker,
    Mission,
    MissionConstraints,
    Shortlist,
    Source,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
)


def _mission() -> Mission:
    return Mission(
        statement="Buy nuclear power names that benefit from AI/data center demand",
        budget_usd=20_000.0,
        constraints=MissionConstraints(
            max_position_pct=0.4,
            max_positions=5,
            time_horizon_months=12,
        ),
    )


def _decomposer(mission_id: str):
    def fn(state):
        return {
            "decomposition": ThesisDecomposition(
                mission_id=mission_id,
                sub_themes=[
                    SubTheme(
                        id="smr",
                        mission_id=mission_id,
                        name="Small modular reactors",
                        hypothesis="SMR commercialization captures data-center load growth through 2030 with $5B+ orders",
                        growth_drivers=["data center power demand"],
                        risks=["regulatory delay"],
                        confidence=0.6,
                        search_keywords=["SMR"],
                    ),
                    SubTheme(
                        id="utility",
                        mission_id=mission_id,
                        name="Existing nuclear utilities",
                        hypothesis="Existing nuclear fleet operators sign premium PPAs with hyperscalers through 2027",
                        growth_drivers=["hyperscaler PPAs"],
                        risks=["regulatory delay"],
                        confidence=0.7,
                        search_keywords=["nuclear PPA"],
                    ),
                ],
                rationale="two non-overlapping sub-themes",
            )
        }
    return fn


def _researcher(mission_id: str):
    """Mock now matches the sequential-loop signature: reads `decomposition`
    from state and returns one assessment per sub-theme in a single call."""
    def fn(state):
        decomp = state["decomposition"]
        out = []
        for st in decomp.sub_themes:
            ticker = "NUSC" if st.id == "smr" else "CEG"
            out.append(SubThemeAssessment(
                mission_id=mission_id,
                sub_theme_id=st.id,
                revised_confidence=0.65,
                key_findings=["finding 1"],
                candidate_tickers=[
                    CandidateTicker(
                        ticker=ticker,
                        company_name=ticker,
                        why_relevant="fits theme",
                        sub_theme_ids=[st.id],
                        mission_id=mission_id,
                    )
                ],
                catalysts=[],
                risks_confirmed=[],
                sources=[Source(kind="url", ref="r", retrieved_at=datetime.now(UTC))],
            ))
        return {"assessments": out}
    return fn


def _shortlist(mission_id: str):
    def fn(state):
        cands = []
        for a in state.get("assessments", []):
            cands.extend(a.candidate_tickers)
        return {
            "shortlist": Shortlist(
                mission_id=mission_id,
                candidates=cands,
                ranking_rationale="merged from assessments",
            )
        }
    return fn


def _build_full_mocked_graph(mission_id: str):
    """Build a graph with every node mocked (no real LLM calls, no disk writes)."""
    from tacapes.nodes.memo_writer import mock_memo_writer
    from tacapes.nodes.portfolio_constructor import mock_portfolio_constructor
    from tacapes.nodes.ta_runner import mock_ta_runner

    return build_graph(
        thesis_decomposer=_decomposer(mission_id),
        subtheme_researcher=_researcher(mission_id),
        shortlist=_shortlist(mission_id),
        ta_runner=mock_ta_runner,
        memo_writer=mock_memo_writer,
        portfolio_constructor=mock_portfolio_constructor,
        persist=lambda state: {},  # no-op for tests
    )


def test_graph_runs_end_to_end_with_mocked_nodes() -> None:
    m = _mission()
    graph = _build_full_mocked_graph(m.id)
    final = graph.invoke({"mission": m})

    # Spine traceability through the entire pipeline.
    assert final["decomposition"].mission_id == m.id
    assert len(final["decomposition"].sub_themes) == 2

    # Parallel fan-out worked: 2 sub-themes → 2 assessments.
    assert len(final["assessments"]) == 2
    assert {a.sub_theme_id for a in final["assessments"]} == {"smr", "utility"}
    assert all(a.mission_id == m.id for a in final["assessments"])

    # Shortlist fan-in worked.
    assert final["shortlist"].mission_id == m.id
    assert {c.ticker for c in final["shortlist"].candidates} == {"NUSC", "CEG"}

    # Per-ticker fan-out worked: 2 candidates → 2 ta_outputs.
    assert len(final["ta_outputs"]) == 2
    assert all(out.mission_id == m.id for out in final["ta_outputs"])
    assert {out.ticker for out in final["ta_outputs"]} == {"NUSC", "CEG"}
    by_ticker = {o.ticker: o for o in final["ta_outputs"]}
    assert by_ticker["NUSC"].subtheme_id == "smr"
    assert by_ticker["CEG"].subtheme_id == "utility"
    assert by_ticker["NUSC"].rating == "Buy"
    assert by_ticker["NUSC"].suggested_position_pct == 0.05
    assert by_ticker["NUSC"].price_target == 100.0

    # Memos: one per ta_output, conviction mapped from rating.
    assert len(final["ta_memos"]) == 2
    memos_by_ticker = {memo.ticker: memo for memo in final["ta_memos"]}
    assert memos_by_ticker["NUSC"].conviction == 5  # Buy → 5
    assert memos_by_ticker["NUSC"].mission_id == m.id
    assert memos_by_ticker["NUSC"].subtheme_id == "smr"

    # Portfolio: cold-start, conviction=5 → Kelly weight 0.25, 2 positions = 0.50.
    portfolio = final["portfolio"]
    assert portfolio.mission_id == m.id
    assert portfolio.mode == "cold_start"
    assert portfolio.total_budget_usd == 20_000.0
    assert len(portfolio.positions) == 2

    weights = {p.ticker: p.weight_pct for p in portfolio.positions}
    assert abs(weights["NUSC"] - 0.25) < 1e-3
    assert abs(weights["CEG"] - 0.25) < 1e-3
    assert abs(portfolio.cash_reserve_pct - 0.50) < 1e-3

    # Notional: $20k * 0.25 = $5k each.
    notionals = {p.ticker: p.notional_usd for p in portfolio.positions}
    assert abs(notionals["NUSC"] - 5_000.0) < 0.01
    assert abs(notionals["CEG"] - 5_000.0) < 0.01

    # Sum invariant: weights + cash = 1.0.
    total = sum(p.weight_pct for p in portfolio.positions) + portfolio.cash_reserve_pct
    assert abs(total - 1.0) < 1e-4


def test_ta_runner_rating_extraction() -> None:
    """Spot-check the regex parsing on a realistic PM markdown."""
    from tacapes.nodes.ta_runner import (
        _extract_horizon,
        _extract_position_pct,
        _extract_price_target,
        _extract_rating,
    )

    md = (
        "**Rating**: Overweight\n\n"
        "**Executive Summary**: Build the position over 2 weeks; size at 7.5% of "
        "the portfolio with stops 8% below entry. Time Horizon: 6-12 months.\n\n"
        "**Investment Thesis**: ...\n\n"
        "**Price Target**: $182.50\n\n"
        "**Time Horizon**: 6-12 months"
    )
    assert _extract_rating(md) == "Overweight"
    assert _extract_position_pct(md) == 0.075
    assert _extract_price_target(md) == 182.5
    assert _extract_horizon(md) == "6-12 months"


def test_ta_runner_rating_fallback_to_hold() -> None:
    from tacapes.nodes.ta_runner import _extract_rating

    assert _extract_rating("no rating word in here at all") == "Hold"


def test_kelly_sizer_clamps_to_max_position_pct() -> None:
    """conviction=5 normally yields 0.25; mission cap of 0.15 should clamp it."""
    from tacapes.nodes.portfolio_constructor import size_positions
    from tacapes.schemas import (
        Catalyst, Driver, InvestmentMemo, KeyNumber, Position, Risk,
        Source, Valuation, ValuationScenario,
    )

    src = Source(kind="internal_model", ref="test", retrieved_at=datetime.now(UTC))
    val = Valuation(
        bear=ValuationScenario(label="bear", methodology="t"),
        base=ValuationScenario(label="base", methodology="t"),
        bull=ValuationScenario(label="bull", methodology="t"),
        current=ValuationScenario(label="current", methodology="t"),
    )

    mission = Mission(
        statement="long enough mission statement for the validator",
        budget_usd=100_000.0,
        constraints=MissionConstraints(
            max_position_pct=0.15,
            max_positions=10,
            time_horizon_months=12,
        ),
    )
    memo = InvestmentMemo(
        ticker="X",
        mission_id=mission.id,
        thesis_one_liner="t",
        conviction=5,
        thesis_alignment="aligned",
        reconciliation_notes="test memo",
        drivers=[Driver(name="d", description="d", importance="primary")],
        risks=[Risk(name="r", description="r", severity="medium", likelihood="medium")],
        catalysts=[Catalyst(name="c", description="c", impact="medium")],
        valuation=val,
        key_numbers=[KeyNumber(label="k", value=0.0, unit="usd", source_doc=src)],
        thesis_breakers=["X reports a 20% revenue miss in next 10-Q"],
        last_refreshed=datetime.now(UTC),
    )
    raw = [Position(ticker="X", weight_pct=0.25, notional_usd=0.0, rationale="r")]
    sized, cash = size_positions(raw, mission=mission, memos_by_ticker={"X": memo})

    assert len(sized) == 1
    assert sized[0].weight_pct == 0.15  # clamped
    assert sized[0].notional_usd == 15_000.0
    assert cash == 0.85


def test_persist_writes_state_to_disk(tmp_path, monkeypatch) -> None:
    from tacapes.nodes.persist import persist
    from tacapes.schemas import TradingAgentsOutput

    monkeypatch.setattr(
        "tacapes.nodes.persist.state_root",
        lambda mid: tmp_path / mid,
    )

    m = _mission()
    ta_out = TradingAgentsOutput(
        ticker="CEG",
        mission_id=m.id,
        subtheme_id="utility",
        trade_date="2026-05-09",
        rating="Buy",
        full_decision_markdown="**Rating**: Buy",
    )
    persist({"mission": m, "ta_outputs": [ta_out]})

    base = tmp_path / m.id
    assert (base / "mission.json").exists()
    assert (base / "ta_outputs" / "CEG.json").exists()
