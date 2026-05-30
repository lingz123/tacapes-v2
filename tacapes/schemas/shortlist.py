"""Shortlist (M4): ranked + deduped candidates across themes."""
from __future__ import annotations

from .common import Strict
from .subtheme import CandidateTicker


class Shortlist(Strict):
    mission_id: str
    candidates: list[CandidateTicker]
    ranking_rationale: str
