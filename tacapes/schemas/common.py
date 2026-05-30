"""
Supporting types shared across schema modules.

Ported from the original tacapes (`src/tacapes/schemas.py`). Kept structurally
identical so the prompts and validation logic port over without translation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal[
    "filing_10k",
    "filing_10q",
    "filing_8k",
    "filing_other",
    "transcript",
    "news",
    "url",
    "internal_model",
]


class Strict(BaseModel):
    """Base for all schemas. `extra='forbid'` makes the contracts gap-free."""

    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    kind: SourceKind
    ref: str
    title: str | None = None
    url: str | None = None
    page: int | None = None
    excerpt: str | None = None
    retrieved_at: datetime


class KeyNumber(Strict):
    label: str
    value: float
    unit: str
    period: str | None = None
    source_doc: Source
    page: int | None = None


class Driver(Strict):
    name: str
    description: str
    importance: Literal["primary", "secondary", "tertiary"] = "secondary"
    evidence: list[Source] = Field(default_factory=list)


class Risk(Strict):
    name: str
    description: str
    severity: Literal["low", "medium", "high"]
    likelihood: Literal["low", "medium", "high"]
    evidence: list[Source] = Field(default_factory=list)


class Catalyst(Strict):
    name: str
    description: str
    expected_window: str | None = None
    impact: Literal["small", "medium", "large"]
    evidence: list[Source] = Field(default_factory=list)


class ValuationScenario(Strict):
    label: Literal["bear", "base", "bull", "current"]
    price_target: float | None = None
    methodology: str
    key_assumptions: list[str] = Field(default_factory=list)


class Valuation(Strict):
    bear: ValuationScenario
    base: ValuationScenario
    bull: ValuationScenario
    current: ValuationScenario


class CorrelationCluster(Strict):
    cluster_id: str
    tickers: list[str]
    rationale: str
    correlation_strength: Literal["weak", "moderate", "strong"]


class WebResult(Strict):
    title: str
    url: str
    snippet: str
    published_at: datetime | None = None


class NewsItem(Strict):
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str | None = None
