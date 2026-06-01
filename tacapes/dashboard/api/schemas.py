"""Pydantic response models for the dashboard JSON API.

These define the *wire shape* the React app sees. They deliberately do
not import `tacapes.schemas` Pydantic models for the LLM pipeline — the
stored JSONB blobs are passed through as `dict[str, Any]` and the React
side treats them according to documentation in `tacapes/schemas/`.

The derived fields (`stat_strip`, `subtheme_summary`, `weak_spots`) are
computed at the API boundary in `routes.py` so the frontend doesn't
re-implement portfolio math.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

MissionStatus = Literal["queued", "running", "done", "failed"]


class PositionPnl(BaseModel):
    ticker: str
    weight_pct: float
    notional_usd: float
    rationale: str | None
    entry_price: float | None
    entry_price_date: str | None
    current_price: float | None
    pnl_pct: float | None


class StatStrip(BaseModel):
    """Top-of-page snapshot for a done mission."""
    invested: float
    current_value: float
    pnl_usd: float | None
    pnl_pct: float | None
    unpriced_count: int
    position_count: int
    cash_reserve_pct: float


class AggregateStats(BaseModel):
    """Cross-mission totals for the list page header strip."""
    invested: float
    current_value: float
    pnl_pct: float | None
    cost: float
    unpriced_count: int


class MissionListItem(BaseModel):
    id: str
    statement: str
    status: MissionStatus
    created_at: datetime
    completed_at: datetime | None
    cost_usd: float | None
    pnl_pct: float | None
    position_count: int


class MissionListResponse(BaseModel):
    missions: list[MissionListItem]
    aggregate: AggregateStats


class SubthemeSummary(BaseModel):
    """The decomposition × assessments × portfolio join the Jinja UI skipped."""
    id: str
    name: str
    description: str | None  # mapped from sub_theme.hypothesis (no `description` field exists)
    confidence: float | None
    candidate_count: int
    chosen_count: int
    chosen_tickers: list[str]
    passed_tickers: list[str]
    key_findings: list[str]


class WeakSpot(BaseModel):
    """Per-ticker flags the React UI shows as icons in memo summary rows."""
    ticker: str
    is_fallback_memo: bool
    is_momentum_trap: bool
    is_losing: bool
    current_pnl_pct: float | None


class MissionDetail(BaseModel):
    """Full mission record. Stage JSONB is passed through verbatim."""
    id: str
    statement: str
    status: MissionStatus
    budget_usd: float
    max_positions: int
    max_position_pct: float
    horizon_months: int
    sectors_excluded: list[str]
    allow_shorts: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    cost_usd: float | None

    # Raw stage outputs. `None` on non-done missions.
    decomposition_json: dict[str, Any] | None = None
    assessments_json: dict[str, Any] | None = None
    shortlist_json: dict[str, Any] | None = None
    ta_outputs_json: dict[str, Any] | None = None
    memos_json: dict[str, Any] | None = None
    portfolio_json: dict[str, Any] | None = None

    # Derivations. Always present (possibly empty).
    positions: list[PositionPnl] = Field(default_factory=list)
    stat_strip: StatStrip | None = None
    subtheme_summary: list[SubthemeSummary] = Field(default_factory=list)
    weak_spots: list[WeakSpot] = Field(default_factory=list)
    chosen_tickers: list[str] = Field(default_factory=list)


class MissionStatusResponse(BaseModel):
    """Lightweight polling endpoint payload."""
    status: MissionStatus
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


class CreateMissionRequest(BaseModel):
    """Body for POST /api/missions. Mirrors MissionConstraints + Mission."""
    statement: str = Field(min_length=20, max_length=2000)
    budget_usd: float = Field(gt=0)
    max_positions: int = Field(ge=1, le=20)
    max_position_pct: float = Field(gt=0, le=1)
    horizon_months: int = Field(ge=1, le=240)
    sectors_excluded: list[str] = Field(default_factory=list)
    allow_shorts: bool = False


class CreateMissionResponse(BaseModel):
    id: str
