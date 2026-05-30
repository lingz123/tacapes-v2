"""
Phase 0 smoke tests: schemas import, instantiate, and the spine works
end-to-end (mission_id propagates from Mission → SubTheme → Memo → Portfolio).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tacapes.schemas import (
    CandidateTicker,
    Catalyst,
    CorrelationCluster,
    Driver,
    InvestmentMemo,
    KeyNumber,
    Mission,
    MissionConstraints,
    PortfolioAllocation,
    PortfolioState,
    Position,
    Risk,
    Shortlist,
    Source,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
    Valuation,
    ValuationScenario,
    is_falsifiable_breaker,
)


def _mk_source() -> Source:
    return Source(
        kind="filing_10k",
        ref="acc-123",
        retrieved_at=datetime.now(UTC),
    )


def _mk_valuation() -> Valuation:
    s = lambda lbl: ValuationScenario(label=lbl, methodology="dcf")
    return Valuation(bear=s("bear"), base=s("base"), bull=s("bull"), current=s("current"))


# ---------------------------------------------------------------------------
# Mission as spine
# ---------------------------------------------------------------------------


def test_mission_gets_uuid_and_timestamp() -> None:
    m = Mission(
        statement="Buy nuclear power names that benefit from AI/data center demand",
        budget_usd=20_000.0,
        constraints=MissionConstraints(
            max_position_pct=0.4,
            max_positions=5,
            time_horizon_months=12,
        ),
    )
    assert len(m.id) == 36  # uuid4 string form
    assert m.created_at.tzinfo is not None  # tz-aware


def test_mission_two_instances_get_distinct_ids() -> None:
    kwargs = dict(
        statement="Buy nuclear power names that benefit from AI/data center demand",
        budget_usd=20_000.0,
        constraints=MissionConstraints(
            max_position_pct=0.4,
            max_positions=5,
            time_horizon_months=12,
        ),
    )
    a = Mission(**kwargs)
    b = Mission(**kwargs)
    assert a.id != b.id  # immutable per-run, not deterministic


def test_mission_rejects_short_statement() -> None:
    with pytest.raises(ValidationError):
        Mission(
            statement="too short",
            budget_usd=20_000.0,
            constraints=MissionConstraints(
                max_position_pct=0.4,
                max_positions=5,
                time_horizon_months=12,
            ),
        )


# ---------------------------------------------------------------------------
# Spine traceability: mission_id propagates downstream
# ---------------------------------------------------------------------------


def test_spine_propagates_through_pipeline() -> None:
    m = Mission(
        statement="Buy nuclear power names that benefit from AI/data center demand",
        budget_usd=20_000.0,
        constraints=MissionConstraints(
            max_position_pct=0.4,
            max_positions=5,
            time_horizon_months=12,
        ),
    )

    sub = SubTheme(
        id="st-1",
        mission_id=m.id,
        name="SMR buildout",
        hypothesis="Small modular reactors capture data center load growth through 2030",
        growth_drivers=["data center power demand"],
        risks=["regulatory delay"],
        confidence=0.6,
        search_keywords=["SMR", "NuScale"],
    )
    assert sub.mission_id == m.id

    decomp = ThesisDecomposition(
        mission_id=m.id, sub_themes=[sub], rationale="three exhaustive sub-themes"
    )
    assert decomp.mission_id == m.id

    cand = CandidateTicker(
        ticker="CEG",
        company_name="Constellation Energy",
        why_relevant="largest US nuclear fleet",
        sub_theme_ids=[sub.id],
        mission_id=m.id,
    )
    sl = Shortlist(mission_id=m.id, candidates=[cand], ranking_rationale="ranked")
    assert sl.mission_id == m.id

    memo = InvestmentMemo(
        ticker="CEG",
        mission_id=m.id,
        subtheme_id=sub.id,
        thesis_one_liner="Nuclear fleet operator with PPA tailwind",
        conviction=4,
        thesis_alignment="aligned",
        reconciliation_notes="TA and thesis both bullish.",
        drivers=[Driver(name="PPA pricing", description="ppa", importance="primary")],
        risks=[Risk(name="reg", description="r", severity="medium", likelihood="low")],
        catalysts=[Catalyst(name="contract", description="c", impact="medium")],
        valuation=_mk_valuation(),
        key_numbers=[KeyNumber(label="rev", value=1.0, unit="usd_b", source_doc=_mk_source())],
        thesis_breakers=["CEG loses 20% of contracted volume in next 10-Q"],
        last_refreshed=datetime.now(UTC),
    )
    assert memo.mission_id == m.id
    assert memo.subtheme_id == sub.id

    alloc = PortfolioAllocation(
        mission_id=m.id,
        total_budget_usd=20_000.0,
        positions=[
            Position(ticker="CEG", weight_pct=0.6, notional_usd=12_000.0, rationale="core"),
            Position(ticker="SMR", weight_pct=0.3, notional_usd=6_000.0, rationale="optionality"),
        ],
        correlation_map=[
            CorrelationCluster(
                cluster_id="nuclear",
                tickers=["CEG", "SMR"],
                rationale="shared regulatory + power-demand drivers",
                correlation_strength="moderate",
            )
        ],
        cash_reserve_pct=0.1,
        rationale="Kelly-fractional with mandate caps",
    )
    assert alloc.mission_id == m.id

    state = PortfolioState(mission_id=m.id, allocation=alloc)
    assert state.mission_id == m.id
    assert state.allocation.mission_id == m.id


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def test_portfolio_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        PortfolioAllocation(
            mission_id="m1",
            total_budget_usd=20_000.0,
            positions=[Position(ticker="X", weight_pct=0.5, notional_usd=10_000.0, rationale="x")],
            cash_reserve_pct=0.2,  # 0.5 + 0.2 != 1.0
            rationale="invalid",
        )


def test_thesis_breaker_falsifiability() -> None:
    assert is_falsifiable_breaker("CEG loses 20% of contracted volume in next 10-Q")
    assert not is_falsifiable_breaker("market conditions deteriorate")
    assert not is_falsifiable_breaker("execution risk materializes")


def test_subtheme_assessment_requires_sources() -> None:
    cand = CandidateTicker(
        ticker="CEG",
        company_name="Constellation Energy",
        why_relevant="x",
        sub_theme_ids=["st-1"],
        mission_id="m1",
    )
    with pytest.raises(ValidationError):
        SubThemeAssessment(
            mission_id="m1",
            sub_theme_id="st-1",
            revised_confidence=0.7,
            key_findings=["k"],
            candidate_tickers=[cand],
            catalysts=[],
            risks_confirmed=[],
            sources=[],  # empty rejected
        )
