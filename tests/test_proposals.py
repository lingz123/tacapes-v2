"""
Phase 3 tests — incremental thesis runs + rebalance proposals.

Three layers, no real LLMs:
- RebalanceProposal/ProposedChange schema round-trip.
- `build_rebalance_proposal` — the deterministic finalize (design §11: pure,
  tested directly): conviction resolution, weight normalization, hold-anchor
  budgeting, unmentioned-held coverage.
- The incremental path end to end: a mocked graph run against an existing
  fund produces + persists a proposal; `apply_proposal` then mutates the fund
  correctly for every action type and keeps the Fund invariant.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tacapes.fund import fund_exists, get_holding, held, load_fund, save_fund, watchlist
from tacapes.graph import build_graph
from tacapes.nodes.portfolio_constructor import (
    _ProposedChangeDraft,
    _RebalanceDraft,
    build_rebalance_proposal,
)
from tacapes.proposals import (
    apply_proposal,
    discard_proposal,
    list_proposals,
    load_proposal,
    save_proposal,
)
from tacapes.schemas import (
    CandidateTicker,
    Fund,
    Holding,
    Mission,
    ProposedChange,
    RebalanceProposal,
    Shortlist,
    Source,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
)

from tests.test_fund import _memo, _mission, cold_start_graph, run_cold_start


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def _held(ticker: str, mission_id: str, *, weight: float, conviction: int = 4) -> Holding:
    now = datetime.now(UTC)
    return Holding(
        ticker=ticker, status="held", weight_pct=weight, notional_usd=weight * 20_000,
        conviction=conviction, ta_rating="Buy", thesis_alignment="aligned",
        thesis_one_liner=f"{ticker} thesis", note="held rationale",
        source_mission_id=mission_id, subtheme_id="smr",
        memo_ref=f"portfolios/{mission_id}/memos/{ticker}.json",
        added_at=now, last_refreshed=now,
    )


def _fund_with(holdings: list[Holding], *, nav: float = 20_000.0) -> Fund:
    """Build a Fund with cash derived so the invariant holds exactly."""
    now = datetime.now(UTC)
    held_w = sum(h.weight_pct for h in holdings if h.status == "held")
    return Fund(
        nav_usd=nav, cash_usd=nav * (1.0 - held_w), holdings=holdings,
        mission_log=[], created_at=now, updated_at=now,
    )


def _change(ticker, action, *, current=0.0, target=0.0, conviction=4, rationale="r") -> ProposedChange:
    return ProposedChange(
        ticker=ticker, action=action, current_weight_pct=current,
        target_weight_pct=target, conviction=conviction, rationale=rationale,
    )


# --- a mocked incremental graph that surfaces brand-new tickers ------------

def _incremental_graph(mission_id: str, tickers: tuple[str, ...]):
    """Fully-mocked graph for an incremental run — the researcher surfaces
    `tickers` (names not in the cold-start fund). Real persist node."""
    from tacapes.nodes.memo_writer import mock_memo_writer
    from tacapes.nodes.portfolio_constructor import mock_portfolio_constructor
    from tacapes.nodes.ta_runner import mock_ta_runner

    def decomposer(state):
        return {"decomposition": ThesisDecomposition(
            mission_id=mission_id,
            sub_themes=[SubTheme(
                id="growth", mission_id=mission_id, name="Advanced reactor startups",
                hypothesis="Advanced reactor startups commercialize through 2032 on AI power demand",
                growth_drivers=["AI power demand"], risks=["funding risk"],
                confidence=0.6, search_keywords=["advanced reactor"],
            )],
            rationale="single sub-theme",
        )}

    def researcher(state):
        return {"assessments": [SubThemeAssessment(
            mission_id=mission_id, sub_theme_id="growth", revised_confidence=0.6,
            key_findings=["finding"],
            candidate_tickers=[
                CandidateTicker(
                    ticker=t, company_name=t, why_relevant="fits theme",
                    sub_theme_ids=["growth"], mission_id=mission_id,
                )
                for t in tickers
            ],
            catalysts=[], risks_confirmed=[],
            sources=[Source(kind="url", ref="r", retrieved_at=datetime.now(UTC))],
        )]}

    def shortlist(state):
        cands = [c for a in state.get("assessments", []) for c in a.candidate_tickers]
        return {"shortlist": Shortlist(
            mission_id=mission_id, candidates=cands, ranking_rationale="merged",
        )}

    return build_graph(
        thesis_decomposer=decomposer,
        subtheme_researcher=researcher,
        shortlist=shortlist,
        ta_runner=mock_ta_runner,
        memo_writer=mock_memo_writer,
        portfolio_constructor=mock_portfolio_constructor,
    )


def run_incremental(
    tmp_path, monkeypatch, *, tickers: tuple[str, ...] = ("OKLO", "SMR"),
) -> tuple[Mission, Fund, RebalanceProposal]:
    """Cold-start a fund, then run a mocked incremental mission against it.
    Returns (incremental_mission, fund_before, proposal)."""
    run_cold_start(tmp_path, monkeypatch)          # writes fund.json (NUSC, CEG)
    fund_before = load_fund()

    m1 = _mission()
    _incremental_graph(m1.id, tickers).invoke({"mission": m1, "fund": fund_before})
    proposal = list_proposals()[0]
    return m1, fund_before, proposal


# ---------------------------------------------------------------------------
# schema round-trip
# ---------------------------------------------------------------------------

def test_proposal_json_round_trip() -> None:
    p = RebalanceProposal(
        mission_id="m-1",
        created_at=datetime.now(UTC),
        changes=[
            _change("NRG", "add", current=0.2, target=0.3, conviction=5),
            _change("OKLO", "new_buy", target=0.1, conviction=4),
            _change("CEG", "exit", current=0.1, conviction=2),
        ],
        cash_after_pct=0.3,
        summary="rotate into OKLO",
    )
    reloaded = RebalanceProposal.model_validate_json(p.model_dump_json())
    assert reloaded.model_dump_json() == p.model_dump_json()
    assert reloaded.status == "pending"
    assert len(reloaded.id) == 36  # uuid4


# ---------------------------------------------------------------------------
# build_rebalance_proposal — the deterministic finalize
# ---------------------------------------------------------------------------

def test_build_proposal_covers_unmentioned_held_with_hold() -> None:
    """A currently-held name absent from the draft is auto-covered as `hold`
    so the weight math is closed."""
    fund = _fund_with([_held("NUSC", "m0", weight=0.25), _held("CEG", "m0", weight=0.25)])
    m = _mission()
    draft = _RebalanceDraft(
        changes=[_ProposedChangeDraft(
            ticker="OKLO", action="new_buy", target_weight_pct=0.2, rationale="new",
        )],
        summary="add OKLO",
    )
    proposal = build_rebalance_proposal(
        draft, mission=m, fund=fund, new_memos=[_memo("OKLO", m.id, conviction=5)],
    )
    by_ticker = {c.ticker: c for c in proposal.changes}
    assert set(by_ticker) == {"OKLO", "NUSC", "CEG"}
    assert by_ticker["NUSC"].action == "hold"
    assert by_ticker["CEG"].action == "hold"
    assert by_ticker["OKLO"].action == "new_buy"
    assert by_ticker["OKLO"].target_weight_pct == 0.2
    # held-after = 0.25 + 0.25 + 0.2 = 0.70 → cash 0.30
    assert abs(proposal.cash_after_pct - 0.30) < 1e-6


def test_build_proposal_normalizes_overweight_buys() -> None:
    """Actionable buys exceeding the budget left by hold anchors get scaled."""
    fund = _fund_with([_held("NUSC", "m0", weight=0.25), _held("CEG", "m0", weight=0.25)])
    m = _mission()  # budget left after anchors = 1 - 0.5 = 0.5
    draft = _RebalanceDraft(
        changes=[
            _ProposedChangeDraft(ticker="AAA", action="new_buy", target_weight_pct=0.4, rationale="a"),
            _ProposedChangeDraft(ticker="BBB", action="new_buy", target_weight_pct=0.4, rationale="b"),
        ],
        summary="two big buys",
    )
    proposal = build_rebalance_proposal(
        draft, mission=m, fund=fund,
        new_memos=[_memo("AAA", m.id, conviction=5), _memo("BBB", m.id, conviction=5)],
    )
    by_ticker = {c.ticker: c for c in proposal.changes}
    # 0.4 + 0.4 = 0.8 scaled to fit budget 0.5 → 0.25 each
    assert abs(by_ticker["AAA"].target_weight_pct - 0.25) < 1e-6
    assert abs(by_ticker["BBB"].target_weight_pct - 0.25) < 1e-6
    assert abs(proposal.cash_after_pct - 0.0) < 1e-6


def test_build_proposal_fresh_memo_supersedes_stored_conviction() -> None:
    """A held ticker re-surfacing in the new thesis takes the fresh memo's
    conviction, not its stored one (design §5.2)."""
    fund = _fund_with([
        _held("NUSC", "m0", weight=0.25, conviction=3),   # stored conviction 3
        _held("CEG", "m0", weight=0.25, conviction=4),
    ])
    m = _mission()
    draft = _RebalanceDraft(
        changes=[_ProposedChangeDraft(
            ticker="NUSC", action="add", target_weight_pct=0.3, rationale="re-surfaced",
        )],
        summary="conviction up",
    )
    proposal = build_rebalance_proposal(
        draft, mission=m, fund=fund,
        new_memos=[_memo("NUSC", m.id, conviction=5)],    # fresh conviction 5
    )
    by_ticker = {c.ticker: c for c in proposal.changes}
    assert by_ticker["NUSC"].conviction == 5      # fresh memo wins
    assert by_ticker["CEG"].conviction == 4       # not re-surfaced → stored


def test_build_proposal_clamps_to_max_position_pct() -> None:
    fund = _fund_with([])  # empty book, all cash
    m = _mission()  # max_position_pct = 0.4
    draft = _RebalanceDraft(
        changes=[_ProposedChangeDraft(
            ticker="AAA", action="new_buy", target_weight_pct=0.9, rationale="huge",
        )],
        summary="oversized buy",
    )
    proposal = build_rebalance_proposal(
        draft, mission=m, fund=fund, new_memos=[_memo("AAA", m.id, conviction=5)],
    )
    assert proposal.changes[0].target_weight_pct == 0.4  # clamped


# ---------------------------------------------------------------------------
# incremental run through the graph
# ---------------------------------------------------------------------------

def test_incremental_run_produces_and_persists_proposal(tmp_path, monkeypatch) -> None:
    m1, fund_before, proposal = run_incremental(tmp_path, monkeypatch)

    # the constructor emitted a proposal, persist saved it, the fund is untouched
    assert proposal.status == "pending"
    assert proposal.mission_id == m1.id
    assert (tmp_path / "proposals" / f"{proposal.id}.json").exists()
    assert {h.ticker for h in load_fund().holdings} == {"NUSC", "CEG"}  # unchanged

    actions = {c.ticker: c.action for c in proposal.changes}
    assert actions["OKLO"] == "new_buy"
    assert actions["SMR"] == "new_buy"
    assert actions["NUSC"] == "hold"   # held, not re-surfaced
    assert actions["CEG"] == "hold"


# ---------------------------------------------------------------------------
# apply_proposal — per-action mutation
# ---------------------------------------------------------------------------

def test_apply_proposal_add_and_trim(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    save_fund(_fund_with([
        _held("NUSC", "m0", weight=0.3), _held("CEG", "m0", weight=0.2),
    ]))
    proposal = RebalanceProposal(
        mission_id="m-incr", created_at=datetime.now(UTC),
        changes=[
            _change("NUSC", "add", current=0.3, target=0.4, conviction=5),
            _change("CEG", "trim", current=0.2, target=0.1, conviction=2),
        ],
        cash_after_pct=0.5, summary="add NUSC, trim CEG",
    )
    save_proposal(proposal)

    fund = apply_proposal(proposal.id)
    assert get_holding(fund, "NUSC").weight_pct == 0.4
    assert get_holding(fund, "NUSC").conviction == 5
    assert get_holding(fund, "CEG").weight_pct == 0.1
    # cash recomputed: 1 - (0.4 + 0.1) = 0.5 → $10,000
    assert abs(fund.cash_usd - 10_000.0) < 1e-6
    Fund.model_validate(fund.model_dump())  # invariant holds


def test_apply_proposal_exit_drops_holding(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    save_fund(_fund_with([
        _held("NUSC", "m0", weight=0.3), _held("CEG", "m0", weight=0.2),
    ]))
    proposal = RebalanceProposal(
        mission_id="m-incr", created_at=datetime.now(UTC),
        changes=[_change("CEG", "exit", current=0.2, target=0.0, conviction=1)],
        cash_after_pct=0.7, summary="exit CEG",
    )
    save_proposal(proposal)

    fund = apply_proposal(proposal.id)
    assert get_holding(fund, "CEG") is None          # dropped entirely
    assert {h.ticker for h in fund.holdings} == {"NUSC"}
    assert abs(fund.cash_usd - 14_000.0) < 1e-6      # 1 - 0.3 = 0.7 of NAV


def test_apply_proposal_hold_is_a_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    save_fund(_fund_with([_held("NUSC", "m0", weight=0.3, conviction=4)]))
    # the change carries conviction 1, but `hold` must leave the holding alone
    proposal = RebalanceProposal(
        mission_id="m-incr", created_at=datetime.now(UTC),
        changes=[_change("NUSC", "hold", current=0.3, target=0.3, conviction=1)],
        cash_after_pct=0.7, summary="hold NUSC",
    )
    save_proposal(proposal)

    fund = apply_proposal(proposal.id)
    assert get_holding(fund, "NUSC").weight_pct == 0.3
    assert get_holding(fund, "NUSC").conviction == 4   # untouched — not 1


def test_apply_proposal_new_buy_and_new_watch(tmp_path, monkeypatch) -> None:
    """new_buy/new_watch build Holdings from the new mission's on-disk memos."""
    m1, _fund_before, _auto = run_incremental(tmp_path, monkeypatch)
    # hand-build a proposal against the same mission folder (memos on disk)
    proposal = RebalanceProposal(
        mission_id=m1.id, created_at=datetime.now(UTC),
        changes=[
            _change("OKLO", "new_buy", target=0.15, conviction=5),
            _change("SMR", "new_watch", target=0.0, conviction=3),
        ],
        cash_after_pct=0.35, summary="buy OKLO, watch SMR",
    )
    save_proposal(proposal)

    fund = apply_proposal(proposal.id)
    oklo = get_holding(fund, "OKLO")
    assert oklo.status == "held"
    assert oklo.weight_pct == 0.15
    assert oklo.notional_usd == 3_000.0
    assert oklo.source_mission_id == m1.id          # lineage to the new mission
    smr = get_holding(fund, "SMR")
    assert smr.status == "watch"
    assert smr.weight_pct == 0.0
    Fund.model_validate(fund.model_dump())          # invariant holds


def test_apply_proposal_logs_mission_and_marks_applied(tmp_path, monkeypatch) -> None:
    m1, _fund_before, proposal = run_incremental(tmp_path, monkeypatch)
    assert len(load_fund().mission_log) == 1        # cold start only

    fund = apply_proposal(proposal.id)
    assert len(fund.mission_log) == 2
    assert fund.mission_log[-1].mission_id == m1.id
    assert fund.mission_log[-1].mode == "incremental"
    assert load_proposal(proposal.id).status == "applied"

    # applying an already-applied proposal is rejected
    with pytest.raises(ValueError, match="not pending"):
        apply_proposal(proposal.id)


def test_apply_proposal_end_to_end_keeps_invariant(tmp_path, monkeypatch) -> None:
    """Full incremental path: cold start → incremental run → apply."""
    m1, _fund_before, proposal = run_incremental(tmp_path, monkeypatch)
    fund = apply_proposal(proposal.id)

    # cold-start NUSC/CEG held + 2 new buys OKLO/SMR
    assert {h.ticker for h in held(fund)} == {"NUSC", "CEG", "OKLO", "SMR"}
    # NUSC/CEG 0.25 each (hold), OKLO/SMR 0.10 each (new_buy) → cash 0.30
    assert abs(fund.cash_usd - 6_000.0) < 1e-6
    Fund.model_validate(fund.model_dump())


# ---------------------------------------------------------------------------
# discard + list
# ---------------------------------------------------------------------------

def test_discard_proposal(tmp_path, monkeypatch) -> None:
    m1, _fund_before, proposal = run_incremental(tmp_path, monkeypatch)
    discarded = discard_proposal(proposal.id)
    assert discarded.status == "discarded"
    assert load_proposal(proposal.id).status == "discarded"

    # a discarded proposal cannot be applied or discarded again
    with pytest.raises(ValueError, match="not pending"):
        apply_proposal(proposal.id)
    with pytest.raises(ValueError, match="not pending"):
        discard_proposal(proposal.id)


def test_list_proposals_newest_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    assert list_proposals() == []
    old = RebalanceProposal(
        mission_id="m-a", created_at=datetime(2026, 1, 1, tzinfo=UTC),
        changes=[], cash_after_pct=1.0, summary="old",
    )
    new = RebalanceProposal(
        mission_id="m-b", created_at=datetime(2026, 5, 1, tzinfo=UTC),
        changes=[], cash_after_pct=1.0, summary="new",
    )
    save_proposal(old)
    save_proposal(new)
    ordered = list_proposals()
    assert [p.summary for p in ordered] == ["new", "old"]
