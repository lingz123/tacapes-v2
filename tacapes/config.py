"""
Centralized config for tacapes-v2.

Wraps TradingAgents' DEFAULT_CONFIG so we always run with:
  - Anthropic provider (Sonnet for quick, Opus for deep)
  - Mission-scoped state paths under ~/.tacapes/portfolios/<mission_id>/ta_*
    so we don't pollute the dependency's ~/.tradingagents/ directory.
"""
from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any


# Models used by TradingAgents internally. TradingAgents builds its own
# ChatAnthropic instances (`tradingagents/llm_clients/anthropic_client.py`),
# bypassing `tacapes/llm.py:get_llm()` and its rate limiter — its passthrough
# kwarg whitelist doesn't even include `rate_limiter`. The ONLY lever we have
# to control TradingAgents' rate-limit risk is model choice.
#
# - deep_think (bull/bear debate, trader decision, risk debate): opus has
#   500K ITPM headroom on this account.
# - quick_think (Market/News/Sentiment/Fundamentals analysts, called many
#   times per debate, fan-outs in parallel across tickers): MUST be haiku,
#   since 4 parallel debates × 4 analysts each × sonnet's 30K ITPM = instant
#   429. Haiku's 50K ITPM + smaller per-call payloads = comfortable.
DEEP_THINK_MODEL = "claude-opus-4-7"
QUICK_THINK_MODEL = "claude-haiku-4-5-20251001"


def tacapes_home() -> Path:
    """Root of all persistent state — the fund, per-mission folders, jobs.

    Defaults to ~/.tacapes. `TACAPES_HOME` overrides it; resolved at call
    time so a single env var redirects every reader/writer (persist,
    artifacts, refresh, fund) — primarily for hermetic tests.
    """
    override = os.environ.get("TACAPES_HOME")
    return Path(override) if override else Path.home() / ".tacapes"


def state_root(mission_id: str) -> Path:
    return tacapes_home() / "portfolios" / mission_id


def make_ta_config(*, mission_id: str) -> dict[str, Any]:
    """Build a TradingAgents config: Anthropic + mission-scoped paths."""
    from tradingagents.default_config import DEFAULT_CONFIG  # noqa: PLC0415

    from .cost import _TRACKER  # noqa: PLC0415

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["llm_provider"] = "anthropic"
    cfg["deep_think_llm"] = DEEP_THINK_MODEL
    cfg["quick_think_llm"] = QUICK_THINK_MODEL
    cfg["max_debate_rounds"] = 1
    cfg["max_risk_discuss_rounds"] = 1

    # Best-effort: TA's AnthropicClient._PASSTHROUGH_KWARGS includes
    # "callbacks", so if TA threads cfg-level callbacks to its LLM kwargs
    # we'll capture its internal spend too. If not, OUR stages are still
    # measured exactly; ta_runner's reported cost will be $0 and we'll
    # know to add a fallback estimator.
    cfg["callbacks"] = [_TRACKER]

    base = state_root(mission_id)
    cfg["results_dir"] = str(base / "ta_logs")
    cfg["data_cache_dir"] = str(base / "ta_cache")
    cfg["memory_log_path"] = str(base / "ta_memory" / "trading_memory.md")

    return cfg
