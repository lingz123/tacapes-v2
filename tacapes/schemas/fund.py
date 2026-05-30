"""
Fund: the persistent book (v2.1).

The Fund is the primary, persistent object — it holds positions and a
watchlist and a log of every thesis applied. It lives at ~/.tacapes/fund.json;
there is exactly one fund (single user). A thesis run is a transaction against
the book; a refresh is an in-place re-evaluation of one holding.

`Position` (portfolio.py) is the constructor's *output* unit. `Holding` is the
persistent *book* unit — richer: it carries health signals refreshed from the
latest memo, and lineage pointers (source_mission_id + subtheme_id) that let a
refresh reload the long-term thesis context without copying it. A single model
covers held positions and watchlist entries via the `status` flag.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from .common import Strict
from .memo import ThesisAlignment
from .portfolio import ConstructorMode
from .ta_output import PortfolioRating


class Holding(Strict):
    """One line of the book. `status` distinguishes held positions from
    watchlist entries — they are 95% identical."""

    ticker: str
    status: Literal["held", "watch"]
    weight_pct: float = Field(default=0.0, ge=0.0, le=1.0)  # of fund NAV; 0 for watch
    notional_usd: float = Field(default=0.0, ge=0.0)        # 0 for watch
    # --- health signals, refreshed from the latest memo ---
    conviction: int = Field(ge=1, le=5)
    ta_rating: PortfolioRating
    thesis_alignment: ThesisAlignment
    thesis_one_liner: str
    note: str                       # rationale (held) | why_not_chosen (watch)
    # --- lineage: lets a refresh run self-contained ---
    source_mission_id: str          # mission that introduced this ticker
    subtheme_id: str | None = None  # for memo_writer reconciliation
    memo_ref: str                   # path under ~/.tacapes/ to the latest memo
    added_at: datetime
    last_refreshed: datetime


class MissionRef(Strict):
    """One entry in the fund's mission log — every thesis ever applied."""

    mission_id: str
    statement: str
    mode: ConstructorMode           # cold_start | incremental
    applied_at: datetime


class Fund(Strict):
    """The book. Exactly one exists per user, at ~/.tacapes/fund.json."""

    schema_version: int = 1         # for future migrations
    nav_usd: float = Field(gt=0.0)  # fixed at creation = first mission budget
    cash_usd: float = Field(ge=0.0)  # uninvested
    holdings: list[Holding] = Field(default_factory=list)  # held + watch
    mission_log: list[MissionRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _weights_and_cash_sum_to_nav(self) -> "Fund":
        """Invariant: held weights + cash fraction == 1.0. NAV is fixed in
        v2.1 — exits and buys redistribute weight within a fixed NAV."""
        held_weight = sum(h.weight_pct for h in self.holdings if h.status == "held")
        total = held_weight + self.cash_usd / self.nav_usd
        if abs(total - 1.0) > 1e-4:
            raise ValueError(
                "held weight_pct + cash_usd/nav_usd must sum to 1.0, "
                f"got {total:.6f}"
            )
        return self


# --- incremental rebalancing (design §4.3) ---------------------------------

ProposedAction = Literal["new_buy", "add", "hold", "trim", "exit", "new_watch"]


class ProposedChange(Strict):
    """One line of a RebalanceProposal — a proposed move on a single ticker.

    `new_buy`/`add`/`trim` resolve to a held Holding at `target_weight_pct`;
    `exit` drops the holding; `new_watch` adds a watchlist line; `hold` is a
    no-op (the holding keeps its current weight and signals)."""

    ticker: str
    action: ProposedAction
    current_weight_pct: float = Field(ge=0.0, le=1.0)
    target_weight_pct: float = Field(ge=0.0, le=1.0)
    conviction: int = Field(ge=1, le=5)
    rationale: str


class RebalanceProposal(Strict):
    """The output of an incremental thesis run — a reviewable set of changes
    against the book. Persisted to ~/.tacapes/proposals/<id>.json; never
    auto-applied (design §4.3)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    mission_id: str
    created_at: datetime
    changes: list[ProposedChange]
    cash_after_pct: float = Field(ge=0.0, le=1.0)
    summary: str
    status: Literal["pending", "applied", "discarded"] = "pending"
