"""
refresh.py — the "regenerate report" operation (v2.1, design §5.1).

Re-evaluates exactly one ticker. The smallest, highest-value v2.1 addition:
it skips the M2/M3/M4 stages entirely. The Holding carries its own lineage
(`source_mission_id` + `subtheme_id`), so a refresh reloads the long-term
thesis context straight from the original mission folder — no copying — runs
one TradingAgents debate, reconciles a fresh memo, and archives the prior
memo under `memos/history/`.

A refresh *reports*; it never trades. It returns a RefreshResult; the caller
updates the Holding's health signals (conviction, alignment, …) but weights
are untouched — a conviction drop just makes the dashboard row go red.

Reusing `make_ta_config(mission_id=source_mission_id)` (via `propagate_one`)
means TradingAgents' cache + reflection memory accumulate in the ticker's
original lineage folder, so refreshes get better over time.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .config import state_root
from .schemas import (
    CandidateTicker,
    Holding,
    InvestmentMemo,
    Mission,
    PortfolioRating,
    Strict,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
    TradingAgentsOutput,
)

# Injectable seams. Defaults hit TradingAgents / an LLM; tests pass mocks.
PropagateFn = Callable[[CandidateTicker, str], TradingAgentsOutput]
WriteMemoFn = Callable[..., tuple[InvestmentMemo, str]]


class RefreshResult(Strict):
    """Outcome of one refresh. `history_ref` is the archived prior memo's path
    relative to the mission folder, or a sentinel if there was no prior memo."""

    ticker: str
    memo: InvestmentMemo
    ta_rating: PortfolioRating
    prior_conviction: int
    new_conviction: int
    memo_source: str  # 'full' | 'fallback-alignment-only' | 'fallback-synthesized'
    history_ref: str


# ---------- lineage reload (all tolerate missing files -> None) ----------

def _load_mission(mission_dir: Path) -> Mission | None:
    p = mission_dir / "mission.json"
    if not p.exists():
        return None
    return Mission.model_validate_json(p.read_text(encoding="utf-8"))


def _load_subtheme(mission_dir: Path, subtheme_id: str | None) -> SubTheme | None:
    if subtheme_id is None:
        return None
    p = mission_dir / "decomposition.json"
    if not p.exists():
        return None
    decomp = ThesisDecomposition.model_validate_json(p.read_text(encoding="utf-8"))
    for st in decomp.sub_themes:
        if st.id == subtheme_id:
            return st
    return None


def _load_assessment(
    mission_dir: Path, subtheme_id: str | None
) -> SubThemeAssessment | None:
    if subtheme_id is None:
        return None
    p = mission_dir / "assessments" / f"{subtheme_id}.json"
    if not p.exists():
        return None
    return SubThemeAssessment.model_validate_json(p.read_text(encoding="utf-8"))


def _archive_prior_memo(mission_dir: Path, ticker: str) -> str | None:
    """Copy the current memo to memos/history/<TICKER>.<ts>.json. Returns the
    archive path relative to the mission folder, or None if no prior memo."""
    current = mission_dir / "memos" / f"{ticker.upper()}.json"
    if not current.exists():
        return None
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    history_dir = mission_dir / "memos" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    archived = history_dir / f"{ticker.upper()}.{ts}.json"
    archived.write_text(current.read_text(encoding="utf-8"), encoding="utf-8")
    return f"memos/history/{archived.name}"


# ---------- default (real) seams ----------

def _default_propagate(cand: CandidateTicker, mission_id: str) -> TradingAgentsOutput:
    from .nodes.ta_runner import propagate_one  # noqa: PLC0415

    return propagate_one(cand, mission_id)


def _default_write_memo(
    *,
    ta_out: TradingAgentsOutput,
    sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None,
    mission_horizon_months: int,
    llm: Any | None,
) -> tuple[InvestmentMemo, str]:
    from .nodes.memo_writer import write_one  # noqa: PLC0415

    if llm is None:
        from .llm import DEFAULT_MODEL, get_llm  # noqa: PLC0415

        llm = get_llm(DEFAULT_MODEL)
    return write_one(
        ta_out=ta_out,
        sub_theme=sub_theme,
        assessment=assessment,
        mission_horizon_months=mission_horizon_months,
        llm=llm,
    )


# ---------- the operation ----------

def refresh_ticker(
    holding: Holding,
    *,
    propagate: PropagateFn | None = None,
    write_memo: WriteMemoFn | None = None,
    llm: Any | None = None,
) -> RefreshResult:
    """Re-evaluate one held/watch holding. See module docstring.

    `propagate` and `write_memo` are injectable seams — the defaults run the
    real TradingAgents debate + LLM reconciliation; tests pass cheap mocks.
    """
    propagate = propagate or _default_propagate
    write_memo = write_memo or _default_write_memo

    mission_dir = state_root(holding.source_mission_id)

    # 1. Minimal candidate carrying the holding's lineage — so the ta_output
    #    is tagged with the original subtheme_id.
    candidate = CandidateTicker(
        ticker=holding.ticker,
        company_name=holding.ticker,
        why_relevant=holding.note,
        sub_theme_ids=[holding.subtheme_id] if holding.subtheme_id else [],
        mission_id=holding.source_mission_id,
    )

    # 2. One TradingAgents debate.
    ta_out = propagate(candidate, holding.source_mission_id)

    # 3. Reload the long-term thesis context from the source mission folder.
    sub_theme = _load_subtheme(mission_dir, holding.subtheme_id)
    assessment = _load_assessment(mission_dir, holding.subtheme_id)
    mission = _load_mission(mission_dir)
    horizon = mission.constraints.time_horizon_months if mission else 12

    # 4. Reconcile a fresh memo against that context.
    memo, memo_source = write_memo(
        ta_out=ta_out,
        sub_theme=sub_theme,
        assessment=assessment,
        mission_horizon_months=horizon,
        llm=llm,
    )

    # 5. Archive the prior memo, write the fresh memo + ta_output, rewrite note.
    #    memos/<TICKER>.json is versioned (prior copy archived to memos/history/);
    #    ta_outputs/<TICKER>.json is a single-slot "latest" artifact (no history
    #    dir in design §3) — overwrite it so the fresh memo's `ta_output_ref`
    #    stays honest and the mission folder stays internally coherent.
    history_ref = _archive_prior_memo(mission_dir, holding.ticker)
    memo_path = mission_dir / "memos" / f"{holding.ticker.upper()}.json"
    memo_path.parent.mkdir(parents=True, exist_ok=True)
    memo_path.write_text(memo.model_dump_json(indent=2), encoding="utf-8")

    ta_path = mission_dir / "ta_outputs" / f"{holding.ticker.upper()}.json"
    ta_path.parent.mkdir(parents=True, exist_ok=True)
    ta_path.write_text(ta_out.model_dump_json(indent=2), encoding="utf-8")

    try:
        from .artifacts import write_ticker_note  # noqa: PLC0415

        write_ticker_note(
            candidate=candidate,
            sub_theme=sub_theme,
            assessment=assessment,
            ta_output=ta_out,
            memo=memo,
        )
    except Exception:
        pass  # cosmetic — the JSON memo above is the source of truth

    return RefreshResult(
        ticker=holding.ticker.upper(),
        memo=memo,
        ta_rating=ta_out.rating,
        prior_conviction=holding.conviction,
        new_conviction=memo.conviction,
        memo_source=memo_source,
        history_ref=history_ref or "(no prior memo)",
    )
