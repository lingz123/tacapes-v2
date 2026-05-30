"""
Anthropic chat model factory.

Lazy imports `langchain_anthropic` so the package can be imported without
the optional dependency installed (tests that override nodes don't need
real LLM access).

Rate limiting: LangGraph fan-outs (subtheme_researcher per sub-theme,
ta_runner per ticker, memo_writer per ta_output) run in parallel within
one process. On Anthropic Tier 1 (30k input tokens/min on sonnet), 3-5
concurrent ReAct agents will trip a 429 within seconds. A module-level
`InMemoryRateLimiter` shared via every `get_llm()` call caps the
collective request rate across all parallel branches.

If you hit 429s with the current settings: lower `requests_per_second`
further, OR upgrade your Anthropic usage tier (Tier 2 is ~80k input
tokens/min on sonnet — large headroom for these defaults).
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.rate_limiters import InMemoryRateLimiter

from .cost import _TRACKER

# Per Anthropic system: Opus 4.7 for deep think, Sonnet 4.6 for quick,
# Haiku 4.5 for high-volume tool-loop work where input-tokens/min on Tier 1
# is the binding constraint (sonnet=30k, opus=20k, haiku=50k ITPM).
DEEP_THINK_MODEL = "claude-opus-4-7"
DEFAULT_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Shared across every ChatAnthropic instance returned by get_llm().
# 0.5 req/sec = 30 req/min steady-state (well under the 50 RPM cap).
# burst=2 lets a single ReAct round (model → tool → model) fire without
# stalling, but no larger so parallel branches can't all hit input-
# tokens-per-minute caps simultaneously. Sized for an account with
# opus=500K, sonnet=30K, haiku=50K ITPM — raise on broader headroom.
_RATE_LIMITER = InMemoryRateLimiter(
    requests_per_second=0.5,
    check_every_n_seconds=0.5,
    max_bucket_size=2,
)


def get_llm(model: str = DEFAULT_MODEL, **kwargs: Any) -> Any:
    """Return a configured ChatAnthropic with shared rate limiter + SDK retries."""
    from langchain_anthropic import ChatAnthropic  # noqa: PLC0415

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file or export it."
        )
    kwargs.setdefault("rate_limiter", _RATE_LIMITER)
    # Anthropic SDK retries on 429 with exponential backoff, respecting
    # the `retry-after` header. Catches anything the rate limiter misses.
    kwargs.setdefault("max_retries", 5)
    # Attach the singleton cost tracker so cli.py can read per-stage spend.
    callbacks = list(kwargs.get("callbacks") or [])
    if _TRACKER not in callbacks:
        callbacks.append(_TRACKER)
    kwargs["callbacks"] = callbacks
    return ChatAnthropic(model=model, api_key=api_key, **kwargs)
