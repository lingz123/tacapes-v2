"""
Mission: the spine of the system.

Every downstream object (SubTheme, Candidate, Memo, PortfolioAllocation,
PortfolioState) carries `mission_id`. v1 treats Missions as immutable —
once created, statement and constraints don't change. The `id` is a UUID4
generated at construction time so two identical statements produce distinct
Missions (the user might reasonably want to start fresh).
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field

from .common import Strict


class MissionConstraints(Strict):
    max_position_pct: float = Field(gt=0.0, le=1.0)
    max_positions: int = Field(ge=1)
    sectors_excluded: list[str] = Field(default_factory=list)
    allow_shorts: bool = False
    time_horizon_months: int = Field(ge=1)


class Mission(Strict):
    id: str = Field(default_factory=lambda: str(uuid4()))
    statement: str = Field(min_length=20)
    budget_usd: float = Field(gt=0.0)
    constraints: MissionConstraints
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
