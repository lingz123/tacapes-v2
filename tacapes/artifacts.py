"""
Markdown artifacts for each mission run.

Two outputs under ~/.tacapes/portfolios/<mission_id>/notes/:
- <TICKER>.md  — per-ticker writeup with three sections:
    1. Why Shortlisted    (sub-theme thesis + research findings, BEFORE TA)
    2. TradingAgents      (the full multi-analyst debate output)
    3. Reconciled Memo    (alignment + drivers/risks/catalysts/valuation)
- _SUMMARY.md  — mission-level overview + portfolio table + index of tickers

Written incrementally from inside memo_writer (per-ticker) and persist
(summary). If a run dies mid-pipeline, the notes for completed tickers
survive on disk.

Keep this module pure — no imports of langchain/langgraph. Just schemas,
filesystem, datetime.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import state_root
from .schemas import (
    CandidateTicker,
    InvestmentMemo,
    Mission,
    PortfolioAllocation,
    Shortlist,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
    TradingAgentsOutput,
)


# ---------- helpers ----------

def _notes_dir(mission_id: str) -> Path:
    p = state_root(mission_id) / "notes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bullets(items: list[str]) -> str:
    if not items:
        return "_(none)_"
    return "\n".join(f"- {x}" for x in items)


def _block_or_none(label: str, body: str | None) -> str:
    if not body:
        return f"### {label}\n\n_(not produced)_"
    return f"### {label}\n\n{body.strip()}"


def _fmt_money(v: float | None) -> str:
    return f"${v:,.2f}" if v is not None else "—"


def _fmt_pct(v: float | None) -> str:
    return f"{v*100:.2f}%" if v is not None else "—"


# ---------- per-ticker render ----------

def render_ticker_md(
    *,
    candidate: CandidateTicker | None,
    sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None,
    ta_output: TradingAgentsOutput,
    memo: InvestmentMemo,
) -> str:
    """Build the full per-ticker writeup. All inputs may be None except
    ta_output and memo, which are always present by construction."""
    parts: list[str] = []

    # --- header ---
    parts.append(f"# {ta_output.ticker} — Investment Memo")
    parts.append("")
    parts.append(f"- **Mission:** `{ta_output.mission_id}`")
    if sub_theme is not None:
        parts.append(f"- **Sub-theme:** `{sub_theme.id}` — {sub_theme.name}")
    parts.append(f"- **Trade date:** {ta_output.trade_date}")
    parts.append(f"- **Generated:** {datetime.now(UTC).isoformat(timespec='seconds')}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # --- 1. why shortlisted ---
    parts.append("## 1. Why Shortlisted")
    parts.append("")
    if candidate is not None:
        parts.append("**Surface rationale:**")
        parts.append("")
        parts.append(f"> {candidate.why_relevant}")
        parts.append("")
    if sub_theme is not None:
        parts.append("**Sub-theme hypothesis (long-term thesis):**")
        parts.append("")
        parts.append(f"> {sub_theme.hypothesis}")
        parts.append("")
        parts.append("**Growth drivers:**")
        parts.append("")
        parts.append(_bullets(sub_theme.growth_drivers))
        parts.append("")
        parts.append("**Sub-theme risks (pre-research):**")
        parts.append("")
        parts.append(_bullets(sub_theme.risks))
        parts.append("")
    if assessment is not None:
        parts.append(
            f"**Research findings** (post-research confidence: "
            f"{assessment.revised_confidence:.2f}):"
        )
        parts.append("")
        parts.append(_bullets(assessment.key_findings))
        parts.append("")
        if assessment.catalysts:
            parts.append("**Research-identified catalysts:**")
            parts.append("")
            parts.append(
                _bullets([
                    f"{c.name} ({c.impact}{', ' + c.expected_window if c.expected_window else ''}): {c.description}"
                    for c in assessment.catalysts
                ])
            )
            parts.append("")
        parts.append("**Risks confirmed by research:**")
        parts.append("")
        parts.append(_bullets(assessment.risks_confirmed))
        parts.append("")

    parts.append("---")
    parts.append("")

    # --- 2. trading agents output ---
    parts.append("## 2. TradingAgents Evaluation")
    parts.append("")
    parts.append(f"- **Rating:** `{ta_output.rating}`")
    parts.append(f"- **Price target:** {_fmt_money(ta_output.price_target)}")
    parts.append(f"- **Time horizon:** {ta_output.time_horizon or '—'}")
    parts.append(
        f"- **Suggested position size:** "
        f"{_fmt_pct(ta_output.suggested_position_pct)}"
    )
    parts.append("")
    parts.append(_block_or_none("Market Report", ta_output.market_report))
    parts.append("")
    parts.append(_block_or_none("Fundamentals Report", ta_output.fundamentals_report))
    parts.append("")
    parts.append(_block_or_none("News Report", ta_output.news_report))
    parts.append("")
    parts.append(_block_or_none("Sentiment Report", ta_output.sentiment_report))
    parts.append("")
    parts.append(_block_or_none("Investment Plan (Research Manager)", ta_output.investment_plan))
    parts.append("")
    parts.append(_block_or_none("Trader's Plan", ta_output.trader_investment_plan))
    parts.append("")
    parts.append(_block_or_none("Risk Debate Judge Decision", ta_output.risk_debate_judge_decision))
    parts.append("")
    parts.append(_block_or_none("Full PM Decision", ta_output.full_decision_markdown))
    parts.append("")

    parts.append("---")
    parts.append("")

    # --- 3. reconciled memo ---
    parts.append("## 3. Reconciled Memo")
    parts.append("")
    parts.append(f"- **Thesis alignment:** `{memo.thesis_alignment}`")
    parts.append(f"- **Final conviction:** **{memo.conviction}/5**")
    parts.append("- **Reconciliation notes:**")
    parts.append("")
    parts.append(f"> {memo.reconciliation_notes}")
    parts.append("")
    parts.append("### Thesis (one-liner)")
    parts.append("")
    parts.append(memo.thesis_one_liner)
    parts.append("")

    # drivers/risks/catalysts as tables
    if memo.drivers:
        parts.append("### Drivers")
        parts.append("")
        parts.append("| Name | Importance | Description |")
        parts.append("| --- | --- | --- |")
        for d in memo.drivers:
            parts.append(f"| {d.name} | {d.importance} | {d.description} |")
        parts.append("")

    if memo.risks:
        parts.append("### Risks")
        parts.append("")
        parts.append("| Name | Severity | Likelihood | Description |")
        parts.append("| --- | --- | --- | --- |")
        for r in memo.risks:
            parts.append(f"| {r.name} | {r.severity} | {r.likelihood} | {r.description} |")
        parts.append("")

    if memo.catalysts:
        parts.append("### Catalysts")
        parts.append("")
        parts.append("| Name | Impact | Expected Window | Description |")
        parts.append("| --- | --- | --- | --- |")
        for c in memo.catalysts:
            parts.append(
                f"| {c.name} | {c.impact} | {c.expected_window or '—'} | {c.description} |"
            )
        parts.append("")

    # valuation table
    parts.append("### Valuation")
    parts.append("")
    parts.append("| Scenario | Price Target | Methodology |")
    parts.append("| --- | --- | --- |")
    for scenario in (memo.valuation.bear, memo.valuation.base, memo.valuation.bull, memo.valuation.current):
        parts.append(
            f"| {scenario.label} | {_fmt_money(scenario.price_target)} | {scenario.methodology} |"
        )
    parts.append("")

    if memo.key_numbers:
        parts.append("### Key Numbers")
        parts.append("")
        for kn in memo.key_numbers:
            parts.append(f"- **{kn.label}**: {kn.value} {kn.unit}" +
                            (f" ({kn.period})" if kn.period else ""))
        parts.append("")

    parts.append("### Thesis Breakers (exit conditions)")
    parts.append("")
    parts.append(_bullets(memo.thesis_breakers))
    parts.append("")

    if memo.sub_agent_audit.get("memo_writer_fallback"):
        parts.append("---")
        parts.append("")
        parts.append("> ⚠️ **Memo synthesis fallback was used for this ticker.** "
                        f"Reason: {memo.sub_agent_audit.get('reason', 'unknown')}. "
                        "Manual review recommended.")

    return "\n".join(parts) + "\n"


def write_ticker_note(
    *,
    candidate: CandidateTicker | None,
    sub_theme: SubTheme | None,
    assessment: SubThemeAssessment | None,
    ta_output: TradingAgentsOutput,
    memo: InvestmentMemo,
) -> Path:
    """Write notes/<TICKER>.md atomically. Returns the path."""
    md = render_ticker_md(
        candidate=candidate, sub_theme=sub_theme, assessment=assessment,
        ta_output=ta_output, memo=memo,
    )
    out_path = _notes_dir(ta_output.mission_id) / f"{ta_output.ticker.upper()}.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path


# ---------- summary render ----------

def render_summary_md(
    *,
    mission: Mission,
    decomposition: ThesisDecomposition | None,
    shortlist: Shortlist | None,
    portfolio: PortfolioAllocation | None,
    memos: list[InvestmentMemo] | None,
    cost_breakdown: list[tuple[str, int, int, float]] | None,
    elapsed_seconds: float | None,
) -> str:
    parts: list[str] = []
    parts.append("# Mission Summary")
    parts.append("")
    parts.append(f"- **Mission ID:** `{mission.id}`")
    parts.append(f"- **Created:** {datetime.now(UTC).isoformat(timespec='seconds')}")
    parts.append(f"- **Statement:** {mission.statement}")
    parts.append(f"- **Budget:** ${mission.budget_usd:,.2f}")
    parts.append(f"- **Horizon:** {mission.constraints.time_horizon_months} months")
    parts.append(f"- **Max positions:** {mission.constraints.max_positions}")
    parts.append(f"- **Max position weight:** {mission.constraints.max_position_pct:.0%}")
    if mission.constraints.sectors_excluded:
        parts.append(f"- **Excluded sectors:** {', '.join(mission.constraints.sectors_excluded)}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # --- sub-themes ---
    if decomposition is not None:
        parts.append(f"## Sub-Themes ({len(decomposition.sub_themes)})")
        parts.append("")
        for st in decomposition.sub_themes:
            parts.append(f"### `{st.id}` — {st.name}")
            parts.append("")
            parts.append(f"> {st.hypothesis}")
            parts.append("")
            parts.append(f"**Pre-research confidence:** {st.confidence:.2f}")
            parts.append("")
            parts.append("**Growth drivers:**")
            parts.append(_bullets(st.growth_drivers))
            parts.append("")
            parts.append("**Risks:**")
            parts.append(_bullets(st.risks))
            parts.append("")
        parts.append("---")
        parts.append("")

    # --- shortlist ---
    if shortlist is not None:
        parts.append(f"## Shortlist ({len(shortlist.candidates)} candidates)")
        parts.append("")
        parts.append("| Ticker | Sub-themes | Why relevant |")
        parts.append("| --- | --- | --- |")
        for c in shortlist.candidates:
            parts.append(
                f"| **{c.ticker}** | {', '.join(c.sub_theme_ids)} | {c.why_relevant} |"
            )
        parts.append("")
        if shortlist.ranking_rationale:
            parts.append(f"**Ranking rationale:** {shortlist.ranking_rationale}")
            parts.append("")
        parts.append("---")
        parts.append("")

    # --- portfolio ---
    if portfolio is not None:
        memos_by_ticker = {m.ticker.upper(): m for m in (memos or [])}
        parts.append(f"## Final Portfolio ({len(portfolio.positions)} positions)")
        parts.append("")
        parts.append("| Ticker | Weight | Notional | Conviction | Alignment | Rationale |")
        parts.append("| --- | --- | --- | --- | --- | --- |")
        for p in portfolio.positions:
            memo = memos_by_ticker.get(p.ticker.upper())
            conv = str(memo.conviction) if memo else "—"
            align = memo.thesis_alignment if memo else "—"
            parts.append(
                f"| **{p.ticker}** | {p.weight_pct*100:.2f}% | "
                f"${p.notional_usd:,.2f} | {conv}/5 | `{align}` | {p.rationale} |"
            )
        # cash row
        cash_notional = portfolio.total_budget_usd * portfolio.cash_reserve_pct
        parts.append(
            f"| **cash** | {portfolio.cash_reserve_pct*100:.2f}% | "
            f"${cash_notional:,.2f} | — | — | reserve |"
        )
        parts.append("")
        parts.append(f"**Portfolio rationale:** {portfolio.rationale}")
        parts.append("")
        parts.append("---")
        parts.append("")

    # --- per-ticker notes index ---
    if memos:
        parts.append("## Per-Ticker Notes")
        parts.append("")
        for memo in sorted(memos, key=lambda m: -m.conviction):
            parts.append(
                f"- [{memo.ticker}]({memo.ticker}.md) — "
                f"conviction **{memo.conviction}/5** · "
                f"`{memo.thesis_alignment}` · "
                f"{memo.thesis_one_liner[:100]}{'...' if len(memo.thesis_one_liner) > 100 else ''}"
            )
        parts.append("")
        parts.append("---")
        parts.append("")

    # --- cost ---
    if cost_breakdown:
        parts.append("## Cost")
        parts.append("")
        parts.append("| Model | Input tokens | Output tokens | USD |")
        parts.append("| --- | ---: | ---: | ---: |")
        total = 0.0
        for model, in_tok, out_tok, usd in cost_breakdown:
            parts.append(f"| `{model}` | {in_tok:,} | {out_tok:,} | ${usd:.2f} |")
            total += usd
        parts.append(f"| **TOTAL** |  |  | **${total:.2f}** |")
        parts.append("")
        if elapsed_seconds is not None:
            mins, secs = divmod(int(elapsed_seconds), 60)
            parts.append(f"**Elapsed:** {mins}m {secs}s")
            parts.append("")

    return "\n".join(parts) + "\n"


def write_summary(
    *,
    mission: Mission,
    decomposition: ThesisDecomposition | None,
    shortlist: Shortlist | None,
    portfolio: PortfolioAllocation | None,
    memos: list[InvestmentMemo] | None,
    cost_breakdown: list[tuple[str, int, int, float]] | None = None,
    elapsed_seconds: float | None = None,
) -> Path:
    md = render_summary_md(
        mission=mission, decomposition=decomposition, shortlist=shortlist,
        portfolio=portfolio, memos=memos,
        cost_breakdown=cost_breakdown, elapsed_seconds=elapsed_seconds,
    )
    out_path = _notes_dir(mission.id) / "_SUMMARY.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path
