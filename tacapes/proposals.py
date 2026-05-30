"""
Proposals — the incremental-run transaction layer (design §5.3).

An incremental `tacapes new` run produces a `RebalanceProposal` (never
auto-applied) persisted to ~/.tacapes/proposals/<id>.json. `apply_proposal`
is the only thing that commits a proposal to the book: it walks the changes,
upserts/drops/adds Holdings, recomputes cash so the Fund invariant holds,
logs the mission, and marks the proposal applied.

`apply_proposal` reads each new ticker's memo + ta_output from the source
mission folder — a `ProposedChange` carries only weights/conviction, not the
full thesis signals needed to build a Holding.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import state_root, tacapes_home
from .fund import _memo_ref, get_holding, load_fund, save_fund, upsert_holding
from .schemas import (
    Fund,
    Holding,
    InvestmentMemo,
    Mission,
    MissionRef,
    ProposedChange,
    RebalanceProposal,
    TradingAgentsOutput,
)


# ---------- paths + IO ----------

def proposals_dir() -> Path:
    return tacapes_home() / "proposals"


def proposal_path(proposal_id: str) -> Path:
    return proposals_dir() / f"{proposal_id}.json"


def save_proposal(proposal: RebalanceProposal) -> Path:
    path = proposal_path(proposal.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_proposal(proposal_id: str) -> RebalanceProposal:
    return RebalanceProposal.model_validate_json(
        proposal_path(proposal_id).read_text(encoding="utf-8")
    )


def list_proposals() -> list[RebalanceProposal]:
    """All proposals on disk, newest first."""
    d = proposals_dir()
    if not d.exists():
        return []
    out = [
        RebalanceProposal.model_validate_json(p.read_text(encoding="utf-8"))
        for p in d.glob("*.json")
    ]
    return sorted(out, key=lambda p: p.created_at, reverse=True)


# ---------- applying a proposal ----------

def _holding_for_change(
    fund: Fund,
    change: ProposedChange,
    mission_id: str,
    *,
    status: str,
) -> Holding:
    """Build the Holding a change resolves to. An existing holding is resized
    in place; a re-surfaced/new ticker takes its thesis signals from the fresh
    memo + ta_output on disk under the source mission folder."""
    tk = change.ticker.upper()
    weight = change.target_weight_pct if status == "held" else 0.0
    notional = round(fund.nav_usd * weight, 2)
    existing = get_holding(fund, tk)

    mission_dir = state_root(mission_id)
    memo_path = mission_dir / "memos" / f"{tk}.json"
    fresh_memo = (
        InvestmentMemo.model_validate_json(memo_path.read_text(encoding="utf-8"))
        if memo_path.exists()
        else None
    )
    now = datetime.now(UTC)

    if fresh_memo is not None:
        # Brand-new buy, or a held name re-surfaced in the new thesis — the
        # fresh memo supersedes the stored signals (design §5.2).
        ta_path = mission_dir / "ta_outputs" / f"{tk}.json"
        if ta_path.exists():
            ta_rating = TradingAgentsOutput.model_validate_json(
                ta_path.read_text(encoding="utf-8")
            ).rating
        else:
            ta_rating = existing.ta_rating if existing is not None else "Hold"
        return Holding(
            ticker=tk,
            status=status,  # type: ignore[arg-type]
            weight_pct=weight,
            notional_usd=notional,
            conviction=change.conviction,
            ta_rating=ta_rating,
            thesis_alignment=fresh_memo.thesis_alignment,
            thesis_one_liner=fresh_memo.thesis_one_liner,
            note=change.rationale,
            source_mission_id=mission_id,
            subtheme_id=fresh_memo.subtheme_id,
            memo_ref=_memo_ref(mission_id, tk),
            added_at=existing.added_at if existing is not None else now,
            last_refreshed=fresh_memo.last_refreshed,
        )

    if existing is not None:
        # An existing holding resized by the rebalance — lineage unchanged.
        return existing.model_copy(update={
            "status": status,
            "weight_pct": weight,
            "notional_usd": notional,
            "conviction": change.conviction,
            "note": change.rationale,
        })

    raise KeyError(
        f"cannot apply change for {tk!r}: no memo on disk and not a holding"
    )


def apply_proposal(proposal_id: str) -> Fund:
    """Commit a pending proposal to the fund (design §5.3). Returns the
    updated Fund. Raises ValueError if the proposal is not pending."""
    proposal = load_proposal(proposal_id)
    if proposal.status != "pending":
        raise ValueError(
            f"proposal {proposal_id} is {proposal.status!r}, not pending"
        )

    fund = load_fund()
    for change in proposal.changes:
        if change.action in ("new_buy", "add", "trim"):
            upsert_holding(
                fund, _holding_for_change(fund, change, proposal.mission_id, status="held")
            )
        elif change.action == "new_watch":
            upsert_holding(
                fund, _holding_for_change(fund, change, proposal.mission_id, status="watch")
            )
        elif change.action == "exit":
            tk = change.ticker.upper()
            fund.holdings = [h for h in fund.holdings if h.ticker.upper() != tk]
        # "hold" → no-op

    # Recompute cash so held weights + cash == NAV (the Fund invariant).
    held_weight = sum(h.weight_pct for h in fund.holdings if h.status == "held")
    fund.cash_usd = fund.nav_usd * max(0.0, 1.0 - held_weight)

    mission_path = state_root(proposal.mission_id) / "mission.json"
    statement = (
        Mission.model_validate_json(mission_path.read_text(encoding="utf-8")).statement
        if mission_path.exists()
        else "(incremental rebalance — mission statement unavailable)"
    )
    fund.mission_log.append(MissionRef(
        mission_id=proposal.mission_id,
        statement=statement,
        mode="incremental",
        applied_at=datetime.now(UTC),
    ))

    # Re-validate before persisting — apply mutates the book, so fail loudly
    # here rather than on the next load if the math somehow broke.
    save_fund(Fund.model_validate(fund.model_dump()))

    proposal.status = "applied"
    save_proposal(proposal)
    return fund


def discard_proposal(proposal_id: str) -> RebalanceProposal:
    """Mark a pending proposal discarded. Raises ValueError if not pending."""
    proposal = load_proposal(proposal_id)
    if proposal.status != "pending":
        raise ValueError(
            f"proposal {proposal_id} is {proposal.status!r}, not pending"
        )
    proposal.status = "discarded"
    save_proposal(proposal)
    return proposal
