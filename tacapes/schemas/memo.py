"""
InvestmentMemo: the central per-ticker artifact.

Wraps TradingAgents' per-ticker output into our structured form so the
portfolio constructor (M6) and any future Monitor/Chat steps consume one
shape regardless of the upstream LLM rig.

Carries both `mission_id` and `subtheme_id` for spine traceability:
position → memo → subtheme → mission.

`thesis_breakers` use a pre-filter heuristic ported from the original
tacapes; the LLM critic remains the real gate (run inside memo_writer).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .common import Driver, KeyNumber, Risk, Strict, Valuation
from .common import Catalyst as Catalyst  # re-export for convenience


ThesisAlignment = Literal[
    "aligned",                  # TA + thesis agree (both bullish or both bearish)
    "short_term_divergence",    # TA bearish, thesis intact (news/sentiment noise)
    "long_term_divergence",     # TA bullish, thesis weakening (momentum trap)
    "fully_diverged",           # TA Hold + thesis ambiguous (no strong stance)
]


VAGUE_BREAKER_PATTERNS: tuple[str, ...] = (
    r"\bsentiment\s+shifts?\b",
    r"\bmarket\s+conditions?\s+(?:change|shift|deteriorate|worsen)",
    r"\bmacro\s+environment\b",
    r"\bcompetitive\s+pressure\b",
    r"\bgeneral\s+(?:slowdown|downturn|weakness)\b",
    r"\bexecution\s+risk\b",
    r"\bunfavou?rab(?:le|ly)\s+macro\b",
    r"\buncertainty\s+(?:rises?|increases?|grows?)",
)

_NUMBER_RE = re.compile(
    r"[><]=?\s*\d|\d+\s*%|\$\s*\d|\d+(?:\.\d+)?\s*(?:bps|bp|x)\b",
    re.IGNORECASE,
)
_SPECIFIC_VERB_RE = re.compile(
    r"\b(?:loses?|wins?|guides?|misses?|cuts?|raises?|cancels?|terminates?|"
    r"announces?|delays?|reports?|files?|exits?|enters?|acquires?|divests?|"
    r"signs?|breaches?|defaults?)\b",
    re.IGNORECASE,
)
_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9.\-]{1,5}\b")


def is_falsifiable_breaker(text: str) -> bool:
    """Heuristic gate: ≥20 chars, no known-vague phrase, has a number/verb/ticker."""
    if len(text.strip()) < 20:
        return False
    for pat in VAGUE_BREAKER_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return False
    return bool(
        _NUMBER_RE.search(text)
        or _SPECIFIC_VERB_RE.search(text)
        or _TICKER_RE.search(text)
    )


class InvestmentMemo(Strict):
    ticker: str
    mission_id: str
    subtheme_id: str | None = None  # null if surfaced cross-theme
    thesis_one_liner: str
    # `conviction` is derived deterministically in memo_writer.py from
    # (ta_rating × thesis_alignment) — see CONVICTION_MATRIX. The LLM
    # never picks this number directly; it picks an alignment category.
    conviction: int = Field(ge=1, le=5)
    thesis_alignment: ThesisAlignment
    reconciliation_notes: str = Field(min_length=1, max_length=600)
    drivers: list[Driver]
    risks: list[Risk]
    catalysts: list[Catalyst]
    valuation: Valuation
    key_numbers: list[KeyNumber]
    thesis_breakers: list[str] = Field(min_length=1)
    last_refreshed: datetime
    ta_output_ref: str | None = None  # path to raw TradingAgents output
    sub_agent_audit: dict[str, Any] = Field(default_factory=dict)

    @field_validator("thesis_breakers")
    @classmethod
    def _validate_breakers(cls, v: list[str]) -> list[str]:
        bad = [b for b in v if not is_falsifiable_breaker(b)]
        if bad:
            raise ValueError(
                "thesis_breakers must be falsifiable; rejected:\n  - "
                + "\n  - ".join(bad)
            )
        return v
