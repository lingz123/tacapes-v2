"""
memo_writer: TradingAgentsOutput[] → InvestmentMemo[].

Reconciles short-term TA signals against the long-term thesis carried by
the original SubTheme + the research-time SubThemeAssessment. The LLM
classifies the alignment into one of 4 categories; Python deterministically
computes `conviction` from the (ta_rating × thesis_alignment) matrix.

Three-layer fallback so a single ticker's structured-output failure cannot
kill the whole run:
  1. Structured `_MemoDraft` call (LLM emits alignment + notes + body).
  2. If that fails after retries: re-ask the LLM for just the alignment
     category (single-field structured output, much harder to fail).
  3. If that fails too: synthesize a fallback memo with neutral alignment
     and content pulled verbatim from the TA reports.

Progress prints per-ticker with elapsed time + current cost. Loops
sequentially over `state["ta_outputs"]`.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from ..prompts import load_prompt
from ..ui import console, working
from ..schemas import (
    Catalyst,
    Driver,
    InvestmentMemo,
    KeyNumber,
    Mission,
    PortfolioRating,
    Risk,
    Source,
    Strict,
    SubTheme,
    SubThemeAssessment,
    ThesisAlignment,
    ThesisDecomposition,
    TradingAgentsOutput,
    Valuation,
    ValuationScenario,
)


# Conviction matrix: (ta_rating, thesis_alignment) -> conviction 1..5.
# Reading: "Buy + aligned" = 5 (full conviction); "Buy + long_term_div"
# = 3 (momentum trap → Hold equivalent); "Sell + short_term_div" = 3
# (TA bearish but thesis intact → Hold, not Sell).
CONVICTION_MATRIX: dict[tuple[PortfolioRating, ThesisAlignment], int] = {
    ("Buy",         "aligned"):                5,
    ("Buy",         "short_term_divergence"):  3,
    ("Buy",         "long_term_divergence"):   3,
    ("Buy",         "fully_diverged"):         2,
    ("Overweight",  "aligned"):                4,
    ("Overweight",  "short_term_divergence"):  3,
    ("Overweight", "long_term_divergence"):    3,
    ("Overweight", "fully_diverged"):          2,
    ("Hold",       "aligned"):                 3,
    ("Hold",       "short_term_divergence"):   3,
    ("Hold",       "long_term_divergence"):    3,
    ("Hold",       "fully_diverged"):          3,
    ("Underweight","aligned"):                 2,
    ("Underweight","short_term_divergence"):   3,
    ("Underweight","long_term_divergence"):    3,
    ("Underweight","fully_diverged"):          2,
    ("Sell",       "aligned"):                 1,
    ("Sell",       "short_term_divergence"):   3,
    ("Sell",       "long_term_divergence"):    2,
    ("Sell",       "fully_diverged"):          1,
}


class _MemoDraft(Strict):
    """LLM-emitted reconciled memo body. Excludes the fields we set
    post-hoc (ticker/mission_id/subtheme_id/conviction/last_refreshed/
    ta_output_ref/sub_agent_audit). Conviction is computed deterministically
    from the matrix above."""

    thesis_one_liner: str
    thesis_alignment: ThesisAlignment
    reconciliation_notes: str = Field(min_length=1, max_length=600)
    drivers: list[Driver]
    risks: list[Risk]
    catalysts: list[Catalyst]
    valuation: Valuation
    key_numbers: list[KeyNumber]
    thesis_breakers: list[str] = Field(min_length=1)


class _AlignmentOnly(Strict):
    """Cheaper fallback prompt target — just the category + notes."""

    thesis_alignment: ThesisAlignment
    reconciliation_notes: str = Field(min_length=1, max_length=600)


def _build_user_message(
    *,
    ta_out: TradingAgentsOutput,
    sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None,
    mission_horizon_months: int,
) -> str:
    """Stitch all reconciliation context into one user message."""
    parts = [
        f"Now: {datetime.now(UTC).isoformat()}",
        f"Mission horizon: {mission_horizon_months} months",
        "",
        "## TradingAgentsOutput (SHORT-TERM signal, past-week analysis):",
        ta_out.model_dump_json(indent=2),
    ]
    if sub_theme is not None:
        parts += [
            "",
            "## SubTheme (LONG-TERM thesis, set before research):",
            sub_theme.model_dump_json(indent=2),
        ]
    if assessment is not None:
        parts += [
            "",
            "## SubThemeAssessment (research-time findings, between long+short):",
            assessment.model_dump_json(indent=2),
        ]
    return "\n".join(parts)


def _synthesize_fallback_memo(
    *,
    ta_out: TradingAgentsOutput,
    reason: str,
) -> InvestmentMemo:
    """Layer-3 fallback: build a memo that always validates, content pulled
    verbatim from the TA report. Conviction = matrix['Hold', 'aligned'] = 3."""
    src = Source(kind="internal_model", ref="memo-writer-fallback", retrieved_at=datetime.now(UTC))
    base_target = ta_out.price_target or 100.0

    def _scen(label: str, mult: float) -> ValuationScenario:
        return ValuationScenario(
            label=label,  # type: ignore[arg-type]
            price_target=base_target * mult if label != "current" else None,
            methodology="fallback: scaled from PM price target",
        )

    # Use the report bodies verbatim as evidence so nothing is lost.
    drivers_blob = (ta_out.fundamentals_report or "")[:400] or "PM bull case (see ta_output_ref for full detail)"
    risks_blob = (ta_out.news_report or "")[:400] or "PM bear case (see ta_output_ref for full detail)"

    return InvestmentMemo(
        ticker=ta_out.ticker,
        mission_id=ta_out.mission_id,
        subtheme_id=ta_out.subtheme_id,
        thesis_one_liner=f"[fallback] PM rating {ta_out.rating} for {ta_out.ticker} — manual review recommended",
        conviction=CONVICTION_MATRIX[("Hold", "aligned")],
        thesis_alignment="aligned",
        reconciliation_notes=f"Memo synthesis fallback ({reason}). Conviction defaulted to neutral 3.",
        drivers=[Driver(name="bull-case (verbatim)", description=drivers_blob, importance="primary")],
        risks=[Risk(name="bear-case (verbatim)", description=risks_blob, severity="medium", likelihood="medium")],
        catalysts=[Catalyst(name="next earnings", description="results in ~90 days", impact="medium")],
        valuation=Valuation(
            bear=_scen("bear", 0.75),
            base=_scen("base", 1.0),
            bull=_scen("bull", 1.25),
            current=_scen("current", 1.0),
        ),
        key_numbers=[KeyNumber(label="price_target", value=base_target, unit="usd", source_doc=src)],
        thesis_breakers=[f"{ta_out.ticker} reports gross margin below 25% in any of the next 4 quarters"],
        last_refreshed=datetime.now(UTC),
        ta_output_ref=f"ta_outputs/{ta_out.ticker}.json",
        sub_agent_audit={"memo_writer_fallback": True, "reason": reason},
    )


def _layer1_full_structured(
    llm: Any, ta_out: TradingAgentsOutput, sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None, mission_horizon_months: int,
) -> _MemoDraft:
    structured = llm.with_structured_output(_MemoDraft)
    user_msg = _build_user_message(
        ta_out=ta_out, sub_theme=sub_theme, assessment=assessment,
        mission_horizon_months=mission_horizon_months,
    )
    return structured.invoke([("system", load_prompt("memo_writer")), ("user", user_msg)])


def _layer2_alignment_only(
    llm: Any, ta_out: TradingAgentsOutput, sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None, mission_horizon_months: int,
) -> _AlignmentOnly:
    """Cheap fallback: ask for just the alignment + notes, no body fields."""
    structured = llm.with_structured_output(_AlignmentOnly)
    user_msg = _build_user_message(
        ta_out=ta_out, sub_theme=sub_theme, assessment=assessment,
        mission_horizon_months=mission_horizon_months,
    )
    system = (
        "You classify the alignment between a TradingAgents per-ticker rating "
        "(short-term) and the user's long-term investment thesis. Pick the "
        "single best `thesis_alignment` category and write 1-2 sentences in "
        "`reconciliation_notes` (≤300 chars). See the user message for definitions."
    )
    return structured.invoke([("system", system), ("user", user_msg)])


def write_one(
    *,
    ta_out: TradingAgentsOutput,
    sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None,
    mission_horizon_months: int,
    llm: Any,
) -> tuple[InvestmentMemo, str]:
    """Reconcile one TradingAgentsOutput into an InvestmentMemo.

    Public primitive — reused by `tacapes/refresh.py` to re-reconcile a single
    ticker. Returns (memo, source_label) where source_label is one of:
    'full', 'fallback-alignment-only', 'fallback-synthesized'."""

    # Layer 1: full structured memo.
    try:
        draft = _layer1_full_structured(
            llm, ta_out, sub_theme, assessment, mission_horizon_months,
        )
        conviction = CONVICTION_MATRIX[(ta_out.rating, draft.thesis_alignment)]
        memo = InvestmentMemo(
            ticker=ta_out.ticker,
            mission_id=ta_out.mission_id,
            subtheme_id=ta_out.subtheme_id,
            thesis_one_liner=draft.thesis_one_liner,
            conviction=conviction,
            thesis_alignment=draft.thesis_alignment,
            reconciliation_notes=draft.reconciliation_notes,
            drivers=draft.drivers,
            risks=draft.risks,
            catalysts=draft.catalysts,
            valuation=draft.valuation,
            key_numbers=draft.key_numbers,
            thesis_breakers=draft.thesis_breakers,
            last_refreshed=datetime.now(UTC),
            ta_output_ref=f"ta_outputs/{ta_out.ticker}.json",
        )
        return memo, "full"
    except Exception as layer1_err:
        layer1_msg = f"{type(layer1_err).__name__}: {layer1_err}"

    # Layer 2: alignment-only.
    try:
        align = _layer2_alignment_only(
            llm, ta_out, sub_theme, assessment, mission_horizon_months,
        )
        # Build a synthesized memo body with the LLM-emitted alignment + notes.
        fallback = _synthesize_fallback_memo(
            ta_out=ta_out,
            reason=f"layer1 failed: {layer1_msg[:120]}; layer2 alignment-only used",
        )
        # Overwrite alignment + conviction + notes with the layer-2 LLM output.
        conviction = CONVICTION_MATRIX[(ta_out.rating, align.thesis_alignment)]
        memo = fallback.model_copy(update={
            "thesis_alignment": align.thesis_alignment,
            "reconciliation_notes": align.reconciliation_notes,
            "conviction": conviction,
        })
        return memo, "fallback-alignment-only"
    except Exception as layer2_err:
        layer2_msg = f"{type(layer2_err).__name__}: {layer2_err}"

    # Layer 3: synthesize entirely.
    return (
        _synthesize_fallback_memo(
            ta_out=ta_out,
            reason=f"layer1: {layer1_msg[:80]}; layer2: {layer2_msg[:80]}",
        ),
        "fallback-synthesized",
    )


def memo_writer(state: dict, *, llm: Any | None = None) -> dict:
    ta_outputs: list[TradingAgentsOutput] = state["ta_outputs"]
    decomp: ThesisDecomposition | None = state.get("decomposition")
    assessments: list[SubThemeAssessment] = state.get("assessments", [])
    shortlist = state.get("shortlist")
    mission: Mission = state["mission"]

    if llm is None:
        from ..llm import DEFAULT_MODEL, get_llm  # noqa: PLC0415
        llm = get_llm(DEFAULT_MODEL)

    # Build lookup tables: subtheme_id -> SubTheme, subtheme_id -> SubThemeAssessment,
    # ticker -> CandidateTicker (for the shortlist's `why_relevant` context).
    sub_themes_by_id: dict[str, SubTheme] = {}
    if decomp is not None:
        sub_themes_by_id = {st.id: st for st in decomp.sub_themes}
    assessments_by_id: dict[str, SubThemeAssessment] = {
        a.sub_theme_id: a for a in assessments
    }
    candidates_by_ticker = {}
    if shortlist is not None:
        candidates_by_ticker = {c.ticker.upper(): c for c in shortlist.candidates}

    n = len(ta_outputs)
    memos: list[InvestmentMemo] = []
    for i, ta_out in enumerate(ta_outputs, 1):
        t0 = time.monotonic()
        sub_theme = sub_themes_by_id.get(ta_out.subtheme_id) if ta_out.subtheme_id else None
        assessment = assessments_by_id.get(ta_out.subtheme_id) if ta_out.subtheme_id else None
        with working(
            f"[{i}/{n}] memo [bold]{ta_out.ticker}[/]  "
            f"(TA=[rating.{ta_out.rating}]{ta_out.rating}[/]) · reconciling against thesis"
        ):
            memo, source = write_one(
                ta_out=ta_out, sub_theme=sub_theme, assessment=assessment,
                mission_horizon_months=mission.constraints.time_horizon_months,
                llm=llm,
            )
        memos.append(memo)

        # Write per-ticker markdown note incrementally — survives partial runs.
        note_warn = ""
        try:
            from ..artifacts import write_ticker_note  # noqa: PLC0415
            write_ticker_note(
                candidate=candidates_by_ticker.get(ta_out.ticker.upper()),
                sub_theme=sub_theme,
                assessment=assessment,
                ta_output=ta_out,
                memo=memo,
            )
        except Exception as e:
            note_warn = f"  [warn](note-writing failed: {type(e).__name__})[/]"

        elapsed = time.monotonic() - t0
        tag = "" if source == "full" else f"  [warn][{source}][/]"
        console.print(
            f"  [ok]✓[/] [{i}/{n}] [bold]{ta_out.ticker}[/]  ·  "
            f"conviction [bold]{memo.conviction}/5[/]  ·  "
            f"[align.{memo.thesis_alignment}]{memo.thesis_alignment}[/]  "
            f"[muted]({elapsed:.0f}s)[/]{tag}{note_warn}"
        )
    return {"ta_memos": memos}


def _mock_one(ta_out: TradingAgentsOutput) -> InvestmentMemo:
    src = Source(kind="internal_model", ref="ta-pipeline", retrieved_at=datetime.now(UTC))
    base_target = ta_out.price_target or 100.0

    def _scen(label: str, mult: float) -> ValuationScenario:
        return ValuationScenario(
            label=label,  # type: ignore[arg-type]
            price_target=base_target * mult if label != "current" else None,
            methodology="phase-3-mock: scaled from PM price target",
        )

    # Mock always emits "aligned" → conviction = MATRIX[rating, "aligned"].
    conviction = CONVICTION_MATRIX[(ta_out.rating, "aligned")]
    return InvestmentMemo(
        ticker=ta_out.ticker,
        mission_id=ta_out.mission_id,
        subtheme_id=ta_out.subtheme_id,
        thesis_one_liner=f"[mock] PM rating {ta_out.rating} for {ta_out.ticker}",
        conviction=conviction,
        thesis_alignment="aligned",
        reconciliation_notes="[mock] aligned by default in test mode",
        drivers=[Driver(name="bull-case", description="from PM thesis", importance="primary")],
        risks=[Risk(name="bear-case", description="from risk team", severity="medium", likelihood="medium")],
        catalysts=[Catalyst(name="next earnings", description="results in ~90 days", impact="medium")],
        valuation=Valuation(
            bear=_scen("bear", 0.75),
            base=_scen("base", 1.0),
            bull=_scen("bull", 1.25),
            current=_scen("current", 1.0),
        ),
        key_numbers=[KeyNumber(label="price_target", value=base_target, unit="usd", source_doc=src)],
        thesis_breakers=[f"{ta_out.ticker} reports a 20% revenue miss in next 10-Q"],
        last_refreshed=datetime.now(UTC),
        ta_output_ref=f"ta_outputs/{ta_out.ticker}.json",
    )


def mock_memo_writer(state: dict) -> dict:
    """Test stand-in: builds one canned InvestmentMemo per ta_output."""
    ta_outputs: list[TradingAgentsOutput] = state["ta_outputs"]
    return {"ta_memos": [_mock_one(o) for o in ta_outputs]}
