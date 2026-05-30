"""
Cost telemetry for the pipeline.

A single `_TRACKER` instance is attached to every ChatAnthropic via
`get_llm(...)` in tacapes/llm.py, and best-effort to TradingAgents'
internal clients via `cfg["callbacks"]` in tacapes/config.py.

Anthropic published prices, USD per million tokens:
    Opus 4.7      input  15.00   output  75.00
    Sonnet 4.6    input   3.00   output  15.00
    Haiku 4.5     input   0.80   output   4.00

The tracker just accumulates `(input_tokens, output_tokens)` per model id.
`snapshot()` returns a frozen copy used to compute per-stage cost in cli.py.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler


_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
}
_DEFAULT_PRICE = (3.00, 15.00)  # fall back to sonnet rates for unknown models


def _usd_for_model(model: str, in_tok: int, out_tok: int) -> float:
    rates = _PRICE_PER_MTOK.get(model, _DEFAULT_PRICE)
    return in_tok * rates[0] / 1_000_000 + out_tok * rates[1] / 1_000_000


@dataclass(frozen=True)
class CostSnapshot:
    """A frozen view of per-model token totals at a point in time."""

    per_model: dict[str, dict[str, int]]  # model -> {input_tokens, output_tokens, ...}

    def total_usd(self) -> float:
        return sum(
            _usd_for_model(
                model,
                d.get("input_tokens", 0) or 0,
                d.get("output_tokens", 0) or 0,
            )
            for model, d in self.per_model.items()
        )

    def cost_since(self, prior: "CostSnapshot") -> float:
        """USD delta between two snapshots (this - prior)."""
        delta = 0.0
        for model, d in self.per_model.items():
            prior_d = prior.per_model.get(model, {})
            in_diff = (d.get("input_tokens", 0) or 0) - (prior_d.get("input_tokens", 0) or 0)
            out_diff = (d.get("output_tokens", 0) or 0) - (prior_d.get("output_tokens", 0) or 0)
            delta += _usd_for_model(model, max(0, in_diff), max(0, out_diff))
        return delta

    def models_used_since(self, prior: "CostSnapshot") -> list[str]:
        out = []
        for model, d in self.per_model.items():
            prior_d = prior.per_model.get(model, {})
            in_diff = (d.get("input_tokens", 0) or 0) - (prior_d.get("input_tokens", 0) or 0)
            out_diff = (d.get("output_tokens", 0) or 0) - (prior_d.get("output_tokens", 0) or 0)
            if in_diff > 0 or out_diff > 0:
                out.append(_short_model_name(model))
        return out

    def breakdown(self) -> list[tuple[str, int, int, float]]:
        """Sorted (model, in_tok, out_tok, usd) tuples, biggest spend first."""
        rows: list[tuple[str, int, int, float]] = []
        for model, d in self.per_model.items():
            in_tok = d.get("input_tokens", 0) or 0
            out_tok = d.get("output_tokens", 0) or 0
            if in_tok == 0 and out_tok == 0:
                continue
            usd = _usd_for_model(model, in_tok, out_tok)
            rows.append((model, in_tok, out_tok, usd))
        rows.sort(key=lambda r: r[3], reverse=True)
        return rows


def _short_model_name(model: str) -> str:
    if "opus" in model:
        return "opus"
    if "sonnet" in model:
        return "sonnet"
    if "haiku" in model:
        return "haiku"
    return model


class CostTracker(UsageMetadataCallbackHandler):
    """LangChain callback handler that accumulates per-model token totals.

    Subclass of langchain's built-in UsageMetadataCallbackHandler which
    populates `self.usage_metadata` dict during every `on_llm_end`. We add
    a snapshot helper and USD cost computation.
    """

    def snapshot(self) -> CostSnapshot:
        return CostSnapshot(per_model=copy.deepcopy(dict(self.usage_metadata)))


# Module-level singleton. Imported by llm.py and config.py.
_TRACKER = CostTracker()
