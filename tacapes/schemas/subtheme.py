"""
Sub-theme decomposition (M2) and per-theme research (M3).

SubTheme carries `mission_id` so the spine traces all the way down.
"""
from __future__ import annotations

from pydantic import Field

from .common import Catalyst, Source, Strict


class SubTheme(Strict):
    id: str
    mission_id: str
    name: str
    hypothesis: str = Field(min_length=20)
    growth_drivers: list[str]
    risks: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    search_keywords: list[str]


class ThesisDecomposition(Strict):
    mission_id: str
    sub_themes: list[SubTheme] = Field(min_length=1)
    rationale: str


class CandidateTicker(Strict):
    ticker: str
    company_name: str
    why_relevant: str
    sub_theme_ids: list[str]
    mission_id: str


class SubThemeAssessment(Strict):
    mission_id: str
    sub_theme_id: str
    revised_confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[str]
    candidate_tickers: list[CandidateTicker]
    catalysts: list[Catalyst]
    risks_confirmed: list[str]
    sources: list[Source] = Field(min_length=1)
