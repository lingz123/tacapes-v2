"""
M6 Portfolio Constructor (Phase 4a).

The LLM emits a `_PortfolioDraft` (positions + correlation_map + rationale)
WITHOUT the strict sum-to-1.0 invariant. Python then:
  1. Filters/sorts positions by memo conviction
  2. Applies fractional-Kelly sizing with KELLY_CAP
  3. Clamps per-position to mission constraint
  4. Computes cash_reserve_pct = 1 - sum(weights)
  5. Builds the strict `PortfolioAllocation` — by construction weights+cash=1.0

This separation matters: the LLM is allowed to propose imperfect raw weights
(real PMs do too), and the deterministic sizer enforces the system invariant.
Previously the LLM emitted PortfolioAllocation directly, which tripped the
strict validator on any draft that summed to ≠1.0 (e.g., 1.05) and killed
the run AT THE LAST STAGE. Lesson: don't use a state-invariant schema as
the parse target for an LLM draft.

Cold-start only for v1. The unified `mode` flag in `PortfolioAllocation`
exists for v2 incremental.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ..prompts import load_prompt
from ..schemas import (
    CorrelationCluster,
    Fund,
    Holding,
    InvestmentMemo,
    Mission,
    PortfolioAllocation,
    Position,
    ProposedAction,
    ProposedChange,
    RebalanceProposal,
    Strict,
)


KELLY_CAP = 0.25  # max single-position fraction even before mandate clamp


class _PortfolioDraft(Strict):
    """LLM-emitted draft. No sum-to-1.0 invariant — that's enforced by the
    deterministic sizer after this parses."""

    positions: list[Position]
    correlation_map: list[CorrelationCluster] = Field(default_factory=list)
    rationale: str


class _ConstructorInput(BaseModel):
    mission: Mission
    memos: list[InvestmentMemo]


def _kelly_weight(conviction: int) -> float:
    """Fractional-Kelly weight from conviction 1..5. Conservative."""
    edge = max(0.0, (conviction - 1) * 0.04 + (0.02 if conviction >= 5 else 0.0))
    raw = edge / 0.04
    return min(KELLY_CAP, raw * 0.10)


def size_positions(
    raw_positions: list[Position],
    *,
    mission: Mission,
    memos_by_ticker: dict[str, InvestmentMemo],
) -> tuple[list[Position], float]:
    """Return (sized_positions, cash_reserve_pct). See module docstring."""
    enriched: list[tuple[int, Position, InvestmentMemo]] = []
    for p in raw_positions:
        memo = memos_by_ticker.get(p.ticker.upper())
        if memo is None or memo.conviction <= 1:
            continue
        enriched.append((memo.conviction, p, memo))
    enriched.sort(key=lambda x: x[0], reverse=True)
    enriched = enriched[: mission.constraints.max_positions]

    weights: dict[str, float] = {}
    for conviction, p, _memo in enriched:
        w = min(_kelly_weight(conviction), mission.constraints.max_position_pct)
        weights[p.ticker.upper()] = w

    total = sum(weights.values())
    if total > 1.0:
        scale = 1.0 / total
        for k in weights:
            weights[k] *= scale
        total = sum(weights.values())

    cash_reserve_pct = max(0.0, 1.0 - total)

    sized: list[Position] = []
    for _conviction, p, _memo in enriched:
        w = weights[p.ticker.upper()]
        sized.append(Position(
            ticker=p.ticker.upper(),
            weight_pct=round(w, 6),
            notional_usd=round(mission.budget_usd * w, 2),
            rationale=p.rationale,
            is_short=False,  # v1 is long-only
        ))
    return sized, round(cash_reserve_pct, 6)


# --- incremental rebalancing (design §4.3 / §5.2) --------------------------

class _IncrementalInput(BaseModel):
    """LLM payload for an incremental run — the new thesis's memos plus the
    current book so the constructor can reason about adds/trims/exits."""

    mission: Mission
    memos: list[InvestmentMemo]
    current_holdings: list[Holding]


class _ProposedChangeDraft(Strict):
    """One LLM-emitted change. Python sets the final conviction + normalized
    weight afterwards — see `build_rebalance_proposal`."""

    ticker: str
    action: ProposedAction
    target_weight_pct: float = Field(ge=0.0, le=1.0)
    rationale: str


class _RebalanceDraft(Strict):
    """LLM-emitted rebalance draft. No invariant — `build_rebalance_proposal`
    normalizes the weights and assembles the strict RebalanceProposal."""

    changes: list[_ProposedChangeDraft]
    summary: str


def build_rebalance_proposal(
    draft: _RebalanceDraft,
    *,
    mission: Mission,
    fund: Fund,
    new_memos: list[InvestmentMemo],
) -> RebalanceProposal:
    """Deterministic finalize of an incremental rebalance.

    The LLM picks the actions + rough target weights; Python sets each
    change's conviction (a fresh memo supersedes the stored holding — §5.2)
    and normalizes the actionable (new_buy/add/trim) weights so they fit the
    budget left by the `hold` anchors. This guarantees held-after weights sum
    to <= 1.0, so a later `apply_proposal` keeps the Fund invariant.
    """
    held_now = {h.ticker.upper(): h for h in fund.holdings if h.status == "held"}
    holdings_by_ticker = {h.ticker.upper(): h for h in fund.holdings}
    memos_by_ticker = {m.ticker.upper(): m for m in new_memos}

    def conviction_of(tk: str) -> int:
        if tk in memos_by_ticker:            # re-surfaced/new → fresh memo wins
            return memos_by_ticker[tk].conviction
        if tk in holdings_by_ticker:
            return holdings_by_ticker[tk].conviction
        return 3

    def current_weight(tk: str) -> float:
        h = held_now.get(tk)
        return h.weight_pct if h is not None else 0.0

    # Cover every currently-held name so the weight math is closed — an
    # unmentioned held name would otherwise float free of the normalization.
    raw: list[tuple[str, ProposedAction, float, str]] = [
        (c.ticker.upper(), c.action, c.target_weight_pct, c.rationale)
        for c in draft.changes
    ]
    covered = {tk for tk, *_ in raw}
    for tk, h in held_now.items():
        if tk not in covered:
            raw.append((tk, "hold", h.weight_pct, "no change proposed"))

    max_pos = mission.constraints.max_position_pct
    anchors = {tk: current_weight(tk) for tk, act, *_ in raw if act == "hold"}
    actionable = {
        tk: min(w, max_pos)
        for tk, act, w, _ in raw
        if act in ("new_buy", "add", "trim")
    }
    budget = max(0.0, 1.0 - sum(anchors.values()))
    act_total = sum(actionable.values())
    if act_total > budget and act_total > 0:
        scale = budget / act_total
        actionable = {tk: w * scale for tk, w in actionable.items()}

    target_of = {**anchors, **actionable}  # held-after ticker -> final weight

    changes: list[ProposedChange] = []
    for tk, act, _raw_w, rationale in raw:
        target = 0.0 if act in ("exit", "new_watch") else target_of.get(tk, 0.0)
        changes.append(ProposedChange(
            ticker=tk,
            action=act,
            current_weight_pct=round(current_weight(tk), 6),
            target_weight_pct=round(target, 6),
            conviction=conviction_of(tk),
            rationale=rationale,
        ))

    cash_after = min(1.0, max(0.0, round(1.0 - sum(target_of.values()), 6)))
    return RebalanceProposal(
        mission_id=mission.id,
        created_at=datetime.now(UTC),
        changes=changes,
        cash_after_pct=cash_after,
        summary=draft.summary,
    )


# --- node entry point ------------------------------------------------------

def portfolio_constructor(
    state: dict,
    *,
    llm: Any | None = None,
) -> dict:
    """Cold-start → PortfolioAllocation; incremental (a `fund` in state) →
    RebalanceProposal."""
    mission: Mission = state["mission"]
    memos: list[InvestmentMemo] = state["ta_memos"]
    fund: Fund | None = state.get("fund")

    if llm is None:
        from ..llm import DEEP_THINK_MODEL, get_llm  # noqa: PLC0415
        llm = get_llm(DEEP_THINK_MODEL)

    if fund is not None:
        # Incremental: emit a reviewable RebalanceProposal against the book.
        structured = llm.with_structured_output(_RebalanceDraft)
        payload = _IncrementalInput(
            mission=mission, memos=memos, current_holdings=fund.holdings
        )
        draft: _RebalanceDraft = structured.invoke([
            ("system", load_prompt("portfolio_constructor_incremental")),
            ("user", payload.model_dump_json(indent=2)),
        ])
        proposal = build_rebalance_proposal(
            draft, mission=mission, fund=fund, new_memos=memos
        )
        return {"proposal": proposal}

    # Cold start: use the draft schema so the LLM's raw weights don't trip the
    # strict sum-to-1.0 validator on PortfolioAllocation. The deterministic
    # sizer below produces a valid final allocation.
    structured = llm.with_structured_output(_PortfolioDraft)
    payload = _ConstructorInput(mission=mission, memos=memos)
    cold_draft: _PortfolioDraft = structured.invoke([
        ("system", load_prompt("portfolio_constructor")),
        ("user", payload.model_dump_json(indent=2)),
    ])

    memos_by_ticker = {m.ticker.upper(): m for m in memos}
    sized, cash_pct = size_positions(
        cold_draft.positions, mission=mission, memos_by_ticker=memos_by_ticker
    )

    final = PortfolioAllocation(
        mission_id=mission.id,
        mode="cold_start",
        total_budget_usd=mission.budget_usd,
        positions=sized,
        correlation_map=cold_draft.correlation_map,
        cash_reserve_pct=cash_pct,
        rationale=cold_draft.rationale,
    )
    return {"portfolio": final}


def mock_portfolio_constructor(state: dict) -> dict:
    """Test stand-in: skips LLM, uses each memo as a single-ticker cluster.

    Cold start → PortfolioAllocation (conviction-weighted Kelly sizing).
    Incremental (a `fund` in state) → RebalanceProposal: each new memo is a
    `new_buy` (or `add` if already held); held names not re-surfaced default
    to `hold` inside `build_rebalance_proposal`.
    """
    mission: Mission = state["mission"]
    memos: list[InvestmentMemo] = state["ta_memos"]
    fund: Fund | None = state.get("fund")

    if fund is not None:
        held_tickers = {h.ticker.upper() for h in fund.holdings if h.status == "held"}
        draft = _RebalanceDraft(
            changes=[
                _ProposedChangeDraft(
                    ticker=m.ticker,
                    action="add" if m.ticker.upper() in held_tickers else "new_buy",
                    target_weight_pct=0.1,
                    rationale=f"[mock] {'add' if m.ticker.upper() in held_tickers else 'new_buy'} {m.ticker}",
                )
                for m in memos
            ],
            summary="[mock] incremental rebalance proposal",
        )
        proposal = build_rebalance_proposal(
            draft, mission=mission, fund=fund, new_memos=memos
        )
        return {"proposal": proposal}

    raw = [
        Position(
            ticker=m.ticker,
            weight_pct=0.1 * m.conviction,  # arbitrary starting guess
            notional_usd=0.0,
            rationale=f"[mock] conviction={m.conviction}",
        )
        for m in memos
    ]
    memos_by_ticker = {m.ticker.upper(): m for m in memos}
    sized, cash_pct = size_positions(raw, mission=mission, memos_by_ticker=memos_by_ticker)

    clusters = [
        CorrelationCluster(
            cluster_id=f"single-{p.ticker.lower()}",
            tickers=[p.ticker],
            rationale="[mock] one-cluster-per-ticker",
            correlation_strength="weak",
        )
        for p in sized
    ]

    final = PortfolioAllocation(
        mission_id=mission.id,
        mode="cold_start",
        total_budget_usd=mission.budget_usd,
        positions=sized,
        correlation_map=clusters,
        cash_reserve_pct=cash_pct,
        rationale="[mock] single-cluster-per-ticker, conviction-weighted Kelly sizing",
    )
    return {"portfolio": final}
