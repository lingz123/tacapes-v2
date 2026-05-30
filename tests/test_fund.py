"""
Phase 1 tests — the persistent Fund (the book).

Three layers, all without real LLMs:
- Fund/Holding/MissionRef schema validation + JSON round-trip.
- `build_fund_from_run` cold-start construction — a pure deterministic
  function (design §11), tested directly.
- `fund.py` IO + the persist node's cold-start fund creation, exercised
  through the fully-mocked LangGraph topology with `TACAPES_HOME` redirected
  to a tmp dir so nothing touches the real ~/.tacapes.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from tacapes.fund import (
    build_fund_from_run,
    fund_exists,
    fund_path,
    get_holding,
    held,
    load_fund,
    save_fund,
    upsert_holding,
    watchlist,
)
from tacapes.graph import build_graph
from tacapes.schemas import (
    CandidateTicker,
    Catalyst,
    Driver,
    Fund,
    Holding,
    InvestmentMemo,
    KeyNumber,
    Mission,
    MissionConstraints,
    MissionRef,
    PortfolioAllocation,
    Position,
    Risk,
    Shortlist,
    Source,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
    TradingAgentsOutput,
    Valuation,
    ValuationScenario,
)


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def _mission(budget: float = 20_000.0) -> Mission:
    return Mission(
        statement="Buy nuclear power names that benefit from AI/data center demand",
        budget_usd=budget,
        constraints=MissionConstraints(
            max_position_pct=0.4,
            max_positions=5,
            time_horizon_months=12,
        ),
    )


def _valuation() -> Valuation:
    s = lambda lbl: ValuationScenario(label=lbl, methodology="dcf")  # noqa: E731
    return Valuation(bear=s("bear"), base=s("base"), bull=s("bull"), current=s("current"))


def _memo(
    ticker: str,
    mission_id: str,
    *,
    conviction: int = 5,
    alignment: str = "aligned",
    subtheme_id: str | None = "smr",
    notes: str = "TA and thesis both bullish.",
) -> InvestmentMemo:
    src = Source(kind="internal_model", ref="t", retrieved_at=datetime.now(UTC))
    return InvestmentMemo(
        ticker=ticker,
        mission_id=mission_id,
        subtheme_id=subtheme_id,
        thesis_one_liner=f"{ticker} long-term thesis one-liner",
        conviction=conviction,
        thesis_alignment=alignment,
        reconciliation_notes=notes,
        drivers=[Driver(name="d", description="d", importance="primary")],
        risks=[Risk(name="r", description="r", severity="medium", likelihood="medium")],
        catalysts=[Catalyst(name="c", description="c", impact="medium")],
        valuation=_valuation(),
        key_numbers=[KeyNumber(label="k", value=1.0, unit="usd", source_doc=src)],
        thesis_breakers=[f"{ticker} reports a 20% revenue miss in next 10-Q"],
        last_refreshed=datetime.now(UTC),
    )


def _ta_output(
    ticker: str, mission_id: str, *, rating: str = "Buy", subtheme_id: str | None = "smr"
) -> TradingAgentsOutput:
    return TradingAgentsOutput(
        ticker=ticker,
        mission_id=mission_id,
        subtheme_id=subtheme_id,
        trade_date="2026-05-15",
        rating=rating,  # type: ignore[arg-type]
        full_decision_markdown=f"**Rating**: {rating}",
    )


def _holding(ticker: str, mission_id: str, *, status: str = "held", weight: float = 0.25) -> Holding:
    now = datetime.now(UTC)
    return Holding(
        ticker=ticker,
        status=status,  # type: ignore[arg-type]
        weight_pct=weight if status == "held" else 0.0,
        notional_usd=weight * 20_000 if status == "held" else 0.0,
        conviction=4,
        ta_rating="Overweight",
        thesis_alignment="aligned",
        thesis_one_liner=f"{ticker} thesis",
        note="rationale",
        source_mission_id=mission_id,
        subtheme_id="smr",
        memo_ref=f"portfolios/{mission_id}/memos/{ticker}.json",
        added_at=now,
        last_refreshed=now,
    )


# --- fully-mocked cold-start graph (no real LLMs, no real TradingAgents) ---

def _decomposer(mission_id: str):
    def fn(state):
        return {"decomposition": ThesisDecomposition(
            mission_id=mission_id,
            sub_themes=[
                SubTheme(
                    id="smr", mission_id=mission_id, name="Small modular reactors",
                    hypothesis="SMR commercialization captures data-center load growth through 2030",
                    growth_drivers=["data center power demand"], risks=["regulatory delay"],
                    confidence=0.6, search_keywords=["SMR"],
                ),
                SubTheme(
                    id="utility", mission_id=mission_id, name="Existing nuclear utilities",
                    hypothesis="Existing nuclear fleet operators sign premium PPAs through 2027",
                    growth_drivers=["hyperscaler PPAs"], risks=["regulatory delay"],
                    confidence=0.7, search_keywords=["nuclear PPA"],
                ),
            ],
            rationale="two non-overlapping sub-themes",
        )}
    return fn


def _researcher(mission_id: str):
    def fn(state):
        out = []
        for st in state["decomposition"].sub_themes:
            ticker = "NUSC" if st.id == "smr" else "CEG"
            out.append(SubThemeAssessment(
                mission_id=mission_id, sub_theme_id=st.id, revised_confidence=0.65,
                key_findings=["finding 1"],
                candidate_tickers=[CandidateTicker(
                    ticker=ticker, company_name=ticker, why_relevant="fits theme",
                    sub_theme_ids=[st.id], mission_id=mission_id,
                )],
                catalysts=[], risks_confirmed=[],
                sources=[Source(kind="url", ref="r", retrieved_at=datetime.now(UTC))],
            ))
        return {"assessments": out}
    return fn


def _shortlist(mission_id: str):
    def fn(state):
        cands = []
        for a in state.get("assessments", []):
            cands.extend(a.candidate_tickers)
        return {"shortlist": Shortlist(
            mission_id=mission_id, candidates=cands, ranking_rationale="merged",
        )}
    return fn


def cold_start_graph(mission_id: str):
    """Fully-mocked graph with the REAL persist node — exercises cold-start
    fund creation end to end."""
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
        # persist: the real node — creates fund.json
    )


def run_cold_start(tmp_path, monkeypatch) -> tuple[Mission, Fund]:
    """Run a mocked cold-start mission under TACAPES_HOME=tmp_path. Returns
    (mission, fund). Shared by test_refresh.py."""
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    m = _mission()
    cold_start_graph(m.id).invoke({"mission": m})
    return m, load_fund()


# ---------------------------------------------------------------------------
# schema validation + round-trip
# ---------------------------------------------------------------------------

def test_holding_json_round_trip() -> None:
    h = _holding("NUSC", "m-1")
    reloaded = Holding.model_validate_json(h.model_dump_json())
    assert reloaded.model_dump_json() == h.model_dump_json()


def test_fund_json_round_trip() -> None:
    now = datetime.now(UTC)
    fund = Fund(
        nav_usd=20_000.0,
        cash_usd=10_000.0,
        holdings=[_holding("NUSC", "m-1", weight=0.25), _holding("CEG", "m-1", weight=0.25)],
        mission_log=[MissionRef(
            mission_id="m-1", statement="a mission statement long enough",
            mode="cold_start", applied_at=now,
        )],
        created_at=now,
        updated_at=now,
    )
    reloaded = Fund.model_validate_json(fund.model_dump_json())
    assert reloaded.model_dump_json() == fund.model_dump_json()
    assert len(reloaded.holdings) == 2
    assert reloaded.mission_log[0].mode == "cold_start"


def test_fund_invariant_rejects_unbalanced_book() -> None:
    """held weight_pct + cash/nav must sum to 1.0."""
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        Fund(
            nav_usd=20_000.0,
            cash_usd=10_000.0,  # 0.50 of NAV
            holdings=[_holding("NUSC", "m-1", weight=0.25)],  # 0.25 held → total 0.75
            mission_log=[],
            created_at=now,
            updated_at=now,
        )


def test_fund_invariant_allows_all_cash_book() -> None:
    """A fund with only watch holdings is 100% cash — still valid."""
    now = datetime.now(UTC)
    fund = Fund(
        nav_usd=20_000.0,
        cash_usd=20_000.0,
        holdings=[_holding("OKLO", "m-1", status="watch")],
        mission_log=[],
        created_at=now,
        updated_at=now,
    )
    assert watchlist(fund) and not held(fund)


def test_holding_rejects_out_of_range_conviction() -> None:
    bad = _holding("NUSC", "m-1").model_dump()
    bad["conviction"] = 9  # conviction is constrained to 1..5
    with pytest.raises(ValidationError):
        Holding.model_validate(bad)


# ---------------------------------------------------------------------------
# build_fund_from_run — pure cold-start construction
# ---------------------------------------------------------------------------

def test_build_fund_splits_held_and_watch() -> None:
    """The constructor picks AAA; BBB is memo'd but unpicked → watchlist."""
    m = _mission(budget=10_000.0)
    portfolio = PortfolioAllocation(
        mission_id=m.id,
        mode="cold_start",
        total_budget_usd=10_000.0,
        positions=[Position(
            ticker="AAA", weight_pct=0.3, notional_usd=3_000.0, rationale="core holding",
        )],
        cash_reserve_pct=0.7,
        rationale="one position",
    )
    memos = [
        _memo("AAA", m.id, conviction=5, notes="picked: strongest conviction"),
        _memo("BBB", m.id, conviction=3, notes="passed over: weaker entry point"),
    ]
    ta_outputs = [
        _ta_output("AAA", m.id, rating="Buy"),
        _ta_output("BBB", m.id, rating="Hold"),
    ]

    fund = build_fund_from_run(
        mission=m, portfolio=portfolio, ta_memos=memos, ta_outputs=ta_outputs,
    )

    assert {h.ticker for h in held(fund)} == {"AAA"}
    assert {h.ticker for h in watchlist(fund)} == {"BBB"}

    aaa = get_holding(fund, "AAA")
    assert aaa.status == "held"
    assert aaa.weight_pct == 0.3
    assert aaa.notional_usd == 3_000.0
    assert aaa.conviction == 5
    assert aaa.ta_rating == "Buy"
    assert aaa.note == "core holding"  # held → position rationale
    assert aaa.memo_ref == f"portfolios/{m.id}/memos/AAA.json"

    bbb = get_holding(fund, "BBB")
    assert bbb.status == "watch"
    assert bbb.weight_pct == 0.0
    assert bbb.notional_usd == 0.0
    assert bbb.conviction == 3
    assert bbb.ta_rating == "Hold"
    assert bbb.note == "passed over: weaker entry point"  # watch → reconciliation notes


def test_build_fund_nav_cash_and_mission_log() -> None:
    m = _mission(budget=10_000.0)
    portfolio = PortfolioAllocation(
        mission_id=m.id,
        mode="cold_start",
        total_budget_usd=10_000.0,
        positions=[Position(
            ticker="AAA", weight_pct=0.3, notional_usd=3_000.0, rationale="core",
        )],
        cash_reserve_pct=0.7,
        rationale="r",
    )
    fund = build_fund_from_run(
        mission=m,
        portfolio=portfolio,
        ta_memos=[_memo("AAA", m.id)],
        ta_outputs=[_ta_output("AAA", m.id)],
    )
    assert fund.nav_usd == 10_000.0           # NAV fixed at the mission budget
    assert fund.cash_usd == 7_000.0           # budget × cash_reserve_pct
    assert fund.schema_version == 1
    assert len(fund.mission_log) == 1
    assert fund.mission_log[0].mission_id == m.id
    assert fund.mission_log[0].mode == "cold_start"
    assert fund.mission_log[0].statement == m.statement


# ---------------------------------------------------------------------------
# fund.py IO + holding helpers (TACAPES_HOME redirected)
# ---------------------------------------------------------------------------

def test_save_and_load_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    m = _mission(budget=10_000.0)
    portfolio = PortfolioAllocation(
        mission_id=m.id, mode="cold_start", total_budget_usd=10_000.0,
        positions=[Position(ticker="AAA", weight_pct=0.3, notional_usd=3_000.0, rationale="r")],
        cash_reserve_pct=0.7, rationale="r",
    )
    fund = build_fund_from_run(
        mission=m, portfolio=portfolio,
        ta_memos=[_memo("AAA", m.id)], ta_outputs=[_ta_output("AAA", m.id)],
    )

    assert not fund_exists()
    path = save_fund(fund)
    assert path == fund_path()
    assert fund_exists()

    reloaded = load_fund()
    assert reloaded.nav_usd == fund.nav_usd
    assert {h.ticker for h in reloaded.holdings} == {h.ticker for h in fund.holdings}


def test_save_fund_stamps_updated_at(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    now = datetime.now(UTC)
    stale = now - timedelta(days=3)
    fund = Fund(
        nav_usd=20_000.0, cash_usd=20_000.0, holdings=[], mission_log=[],
        created_at=stale, updated_at=stale,
    )
    save_fund(fund)
    assert load_fund().updated_at > stale


def test_upsert_and_get_holding_are_case_insensitive() -> None:
    now = datetime.now(UTC)
    fund = Fund(
        nav_usd=20_000.0, cash_usd=20_000.0, holdings=[], mission_log=[],
        created_at=now, updated_at=now,
    )
    h = _holding("NUSC", "m-1", status="watch")
    upsert_holding(fund, h)
    assert len(fund.holdings) == 1
    assert get_holding(fund, "nusc") is not None  # case-insensitive lookup

    # upsert with the same ticker replaces, does not append
    updated = h.model_copy(update={"conviction": 2})
    upsert_holding(fund, updated)
    assert len(fund.holdings) == 1
    assert get_holding(fund, "NUSC").conviction == 2
    assert get_holding(fund, "MISSING") is None


# ---------------------------------------------------------------------------
# persist node — cold-start fund creation through the real graph
# ---------------------------------------------------------------------------

def test_persist_creates_fund_on_cold_start(tmp_path, monkeypatch) -> None:
    m, fund = run_cold_start(tmp_path, monkeypatch)

    assert fund_exists()
    assert fund.nav_usd == 20_000.0
    # mock pipeline: 2 candidates, both picked (max_positions=5) → 2 held, 0 watch
    assert {h.ticker for h in held(fund)} == {"NUSC", "CEG"}
    assert watchlist(fund) == []
    assert all(h.source_mission_id == m.id for h in fund.holdings)
    assert fund.mission_log[0].mission_id == m.id

    # the fund file is real JSON on disk and re-validates
    assert (tmp_path / "fund.json").exists()
    Fund.model_validate_json((tmp_path / "fund.json").read_text())


def test_persist_does_not_overwrite_existing_fund(tmp_path, monkeypatch) -> None:
    """Phase 1: incremental runs are deferred — a second run must leave the
    existing fund untouched (no clobber)."""
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    now = datetime.now(UTC)
    sentinel = Fund(
        nav_usd=999.0, cash_usd=999.0, holdings=[], mission_log=[],
        created_at=now, updated_at=now,
    )
    save_fund(sentinel)

    m = _mission()
    cold_start_graph(m.id).invoke({"mission": m})

    after = load_fund()
    assert after.nav_usd == 999.0           # untouched — not rebuilt from the run
    assert after.holdings == []
