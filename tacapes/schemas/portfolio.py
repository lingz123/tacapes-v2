"""
Portfolio output (M6) and persistent state.

PortfolioAllocation = the constructor's output for one mission.
PortfolioState = what we persist to ~/.tacapes/portfolios/<mission_id>/.

Validators enforce that position weights + cash_reserve_pct sum to 1.0
(within a small tolerance).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import CorrelationCluster, Strict


class Position(Strict):
    ticker: str
    weight_pct: float = Field(ge=0.0, le=1.0)
    notional_usd: float = Field(ge=0.0)
    rationale: str
    is_short: bool = False


ConstructorMode = Literal["cold_start", "incremental"]


class PortfolioAllocation(Strict):
    mission_id: str
    mode: ConstructorMode = "cold_start"
    total_budget_usd: float = Field(gt=0.0)
    positions: list[Position]
    correlation_map: list[CorrelationCluster] = Field(default_factory=list)
    cash_reserve_pct: float = Field(ge=0.0, le=1.0)
    rationale: str

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "PortfolioAllocation":
        total = sum(p.weight_pct for p in self.positions) + self.cash_reserve_pct
        if abs(total - 1.0) > 1e-4:
            raise ValueError(
                f"position weights + cash_reserve_pct must sum to 1.0, got {total:.6f}"
            )
        return self


class PortfolioState(Strict):
    """Persisted snapshot. v1 writes this once at end of cold-start run."""

    mission_id: str
    allocation: PortfolioAllocation
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
