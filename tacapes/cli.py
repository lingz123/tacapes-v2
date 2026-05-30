"""
CLI entry point for tacapes-v2.

  $ tacapes preflight                                # verify API access
  $ tacapes new "Buy nuclear power names ..." \\
        --budget 20000                               # run a full mission

Rich-based terminal UI. Per-stage panels, sub-theme tree, live spinners
during ta_runner / memo_writer, polished portfolio + cost tables. Per-ticker
markdown artifacts written incrementally to ~/.tacapes/portfolios/<id>/notes/.
"""
from __future__ import annotations

# Filter third-party warning noise before anything else imports the offending
# modules. Both warnings are cosmetic — the underlying code is fine.
import warnings as _warnings
_warnings.filterwarnings(
    "ignore",
    message=r"Model '.*' is not in the known model list",
    category=RuntimeWarning,
)
_warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects`",
)

import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

# Heavy imports (langgraph, langchain_anthropic, schemas pulling pydantic-core)
# stay lazy inside command bodies so `tacapes --help` and `tacapes preflight`
# start in <1s instead of paying the langgraph cold-import cost.
from .ui import (
    console,
    cost_tag,
    fail_line,
    ok_line,
    print_artifacts_path,
    print_banner,
    print_cost_table,
    print_mission_card,
    print_portfolio_table,
    print_shortlist_table,
    print_subtheme_tree,
    skipped_line,
    stage_panel,
    working,
)

app = typer.Typer(help="Mission-driven portfolio builder")

REQUIRED_ENV_VARS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "NEWSAPI_KEY")


def _missing_env_vars() -> list[str]:
    return [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]


# ---------- per-stage summary lines ----------

def _print_stage_done(
    node_name: str, update: dict | None, stage_cost: float, models: list[str]
) -> None:
    """One ✓-prefixed bold summary line + any data-specific rendering."""
    update = update or {}
    tag = cost_tag(stage_cost, models)

    if node_name == "thesis_decomposer":
        d = update.get("decomposition")
        if d is None:
            skipped_line("no decomposition emitted", tag)
            return
        ok_line(f"[bold]{len(d.sub_themes)}[/] sub-themes identified", tag)
        console.print()
        print_subtheme_tree(d)
        console.print()

    elif node_name == "subtheme_researcher":
        assessments = update.get("assessments") or []
        total = sum(len(a.candidate_tickers) for a in assessments)
        ok_line(
            f"[bold]{total}[/] candidate proposals across "
            f"[bold]{len(assessments)}[/] sub-themes",
            tag,
        )

    elif node_name == "shortlist":
        sl = update.get("shortlist")
        if sl is None:
            skipped_line("no shortlist emitted", tag)
            return
        ok_line(f"[bold]{len(sl.candidates)}[/] candidates after dedupe", tag)
        console.print()
        print_shortlist_table(sl)
        console.print()

    elif node_name == "ta_runner":
        outs = update.get("ta_outputs") or []
        ratings = Counter(o.rating for o in outs)
        order = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
        rating_str = "  ".join(
            f"[rating.{k}]{k}={v}[/]"
            for k, v in sorted(ratings.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
        )
        ok_line(
            f"[bold]{len(outs)}[/] tickers evaluated  ·  {rating_str}",
            tag,
        )

    elif node_name == "memo_writer":
        memos = update.get("ta_memos") or []
        if not memos:
            skipped_line("no memos emitted", tag)
            return
        alignments = Counter(m.thesis_alignment for m in memos)
        align_str = "  ".join(
            f"[align.{k}]{k}[/]=[bold]{v}[/]" for k, v in alignments.items()
        )
        convictions = [m.conviction for m in memos]
        ok_line(
            f"[bold]{len(memos)}[/] memos  ·  {align_str}  "
            f"·  conviction {min(convictions)}–{max(convictions)} "
            f"(mean {sum(convictions)/len(convictions):.1f})",
            tag,
        )

    elif node_name == "portfolio_constructor":
        p = update.get("portfolio")
        prop = update.get("proposal")
        if p is not None:
            ok_line(
                f"[bold]{len(p.positions)}[/] positions  ·  "
                f"cash reserve [bold]{p.cash_reserve_pct*100:.1f}%[/]",
                tag,
            )
        elif prop is not None:
            acts = Counter(c.action for c in prop.changes)
            act_str = "  ".join(f"{k}=[bold]{v}[/]" for k, v in acts.items())
            ok_line(
                f"rebalance proposal  ·  [bold]{len(prop.changes)}[/] changes  ·  "
                f"{act_str}",
                tag,
            )
        else:
            skipped_line("no portfolio or proposal emitted", tag)
            return

    elif node_name == "persist":
        ok_line("artifacts saved to disk", tag)

    else:
        ok_line(f"{node_name}: {list(update.keys())}", tag)


# ---------- commands ----------

@app.command()
def new(
    statement: str = typer.Argument(..., help="The mission statement (≥20 chars)"),
    budget: float = typer.Option(20000.0, "--budget", help="Total capital in USD"),
    max_position_pct: float = typer.Option(
        0.4, "--max-pos-pct", help="Max single-position fraction (0..1)"
    ),
    max_positions: int = typer.Option(
        5, "--max-positions", help="Max number of positions"
    ),
    horizon_months: int = typer.Option(
        12, "--horizon", help="Time horizon in months"
    ),
    excluded: list[str] = typer.Option(
        [], "--exclude", help="Sectors to exclude (repeatable)"
    ),
) -> None:
    """Run a mission end-to-end.

    No fund yet → cold start (creates the persistent fund). A fund already
    exists → incremental: produces a reviewable RebalanceProposal, committed
    with `tacapes apply <id>`.
    """
    load_dotenv()
    missing = _missing_env_vars()
    if missing:
        console.print(
            f"[err]Missing required env vars:[/] {', '.join(missing)}.  "
            "Add them to .env (see .env.example) or export them."
        )
        raise typer.Exit(code=1)

    from .cost import _TRACKER
    from .fund import fund_exists, held, load_fund, watchlist
    from .graph import build_graph
    from .schemas import Mission, MissionConstraints

    # No fund → cold start; an existing fund → incremental (position-aware).
    current_fund = load_fund() if fund_exists() else None

    mission = Mission(
        statement=statement,
        budget_usd=budget,
        constraints=MissionConstraints(
            max_position_pct=max_position_pct,
            max_positions=max_positions,
            sectors_excluded=list(excluded),
            time_horizon_months=horizon_months,
        ),
    )

    print_banner()
    print_mission_card(mission, horizon_months)

    graph = build_graph()
    final_state: dict[str, Any] = {}
    last_snap = _TRACKER.snapshot()
    t0 = time.monotonic()
    stages_seen: set[str] = set()

    initial_state: dict[str, Any] = {"mission": mission}
    if current_fund is not None:
        initial_state["fund"] = current_fund

    for chunk in graph.stream(initial_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if node_name not in stages_seen:
                stage_panel(node_name)
                stages_seen.add(node_name)

            current = _TRACKER.snapshot()
            stage_cost = current.cost_since(last_snap)
            models = current.models_used_since(last_snap)
            last_snap = current
            _print_stage_done(node_name, update, stage_cost, models)
            if update:
                final_state.update(update)

    console.print()
    elapsed = time.monotonic() - t0

    from .config import tacapes_home

    def _print_artifacts() -> None:
        notes_dir = tacapes_home() / "portfolios" / mission.id / "notes"
        if notes_dir.exists():
            n_notes = sum(1 for p in notes_dir.glob("*.md") if p.name != "_SUMMARY.md")
            print_artifacts_path(
                notes_dir, n_notes, (notes_dir / "_SUMMARY.md").exists()
            )
        console.print()

    if current_fund is None:
        # Cold start — expect a portfolio and a freshly created fund.
        portfolio = final_state.get("portfolio")
        if portfolio is None:
            fail_line("No portfolio produced.")
            print_cost_table(_TRACKER.snapshot(), elapsed)
            raise typer.Exit(code=1)
        print_portfolio_table(portfolio, final_state.get("ta_memos") or [])
        console.print()
        print_cost_table(_TRACKER.snapshot(), elapsed)
        console.print()
        _print_artifacts()
        if fund_exists():
            the_fund = load_fund()
            console.print(
                f"  [ok]✓[/] fund created  ·  [bold]{len(held(the_fund))}[/] held  ·  "
                f"[bold]{len(watchlist(the_fund))}[/] watch  "
                f"[muted](tacapes fund · tacapes refresh <TICKER>)[/]"
            )
            console.print()
    else:
        # Incremental — expect a reviewable RebalanceProposal.
        proposal = final_state.get("proposal")
        if proposal is None:
            fail_line("No rebalance proposal produced.")
            print_cost_table(_TRACKER.snapshot(), elapsed)
            raise typer.Exit(code=1)
        from .ui import print_proposal

        print_proposal(proposal)
        console.print()
        print_cost_table(_TRACKER.snapshot(), elapsed)
        console.print()
        _print_artifacts()
        console.print(
            f"  [ok]✓[/] proposal [bold]{proposal.id}[/] saved  "
            f"[muted](apply: tacapes apply {proposal.id})[/]"
        )
        console.print()


@app.command()
def fund() -> None:
    """Print the current persistent fund — the book (held + watchlist)."""
    from .fund import fund_exists, load_fund
    from .ui import print_fund

    print_banner()
    if not fund_exists():
        console.print(
            '  [warn]No fund yet.[/]  Run [bold cyan]tacapes new "<thesis>"[/] '
            "to cold-start the book."
        )
        console.print()
        return
    print_fund(load_fund())


@app.command()
def refresh(
    ticker: str = typer.Argument(..., help="Ticker of a held/watch holding"),
) -> None:
    """Re-evaluate one held/watch holding and update the fund.

    Skips M2/M3/M4 — re-runs only the TradingAgents debate + memo
    reconciliation for this ticker, archives the prior memo, and writes the
    refreshed conviction/alignment back to the fund. Weights are untouched.
    """
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[err]Missing required env var:[/] ANTHROPIC_API_KEY.  "
            "Add it to .env (see .env.example) or export it."
        )
        raise typer.Exit(code=1)

    from .fund import fund_exists, get_holding, load_fund, refresh_holding, save_fund
    from .refresh import refresh_ticker

    print_banner()

    if not fund_exists():
        console.print(
            '  [warn]No fund yet.[/]  Run [bold cyan]tacapes new "<thesis>"[/] first.'
        )
        raise typer.Exit(code=1)

    fund = load_fund()
    holding = get_holding(fund, ticker)
    if holding is None:
        console.print(
            f"  [err]✗[/] [bold]{ticker.upper()}[/] is not in the fund.  "
            "Run [bold cyan]tacapes fund[/] to see the book."
        )
        raise typer.Exit(code=1)

    console.print(
        f"[bold cyan]refresh[/]  [muted]· re-evaluating "
        f"{holding.ticker} ({holding.status})[/]"
    )
    console.rule(style="dim cyan")
    console.print()

    t0 = time.monotonic()
    with working(
        f"[bold]{holding.ticker}[/] · TradingAgents debate + memo reconciliation"
    ):
        result = refresh_ticker(holding)
    elapsed = time.monotonic() - t0

    refresh_holding(
        fund, ticker=holding.ticker, memo=result.memo, ta_rating=result.ta_rating
    )
    save_fund(fund)

    delta = result.new_conviction - result.prior_conviction
    arrow = "[ok]▲[/]" if delta > 0 else ("[err]▼[/]" if delta < 0 else "[muted]·[/]")
    console.print(
        f"  [ok]✓[/] [bold]{result.ticker}[/]  ·  conviction "
        f"{result.prior_conviction} → [bold]{result.new_conviction}[/]/5 {arrow}  ·  "
        f"[rating.{result.ta_rating}]{result.ta_rating}[/]  ·  "
        f"[align.{result.memo.thesis_alignment}]{result.memo.thesis_alignment}[/]  "
        f"[muted]({elapsed:.0f}s)[/]"
    )
    if result.history_ref != "(no prior memo)":
        console.print(f"  [muted]prior memo archived → {result.history_ref}[/]")
    if result.memo_source != "full":
        console.print(f"  [warn]memo fallback used: {result.memo_source}[/]")
    console.print()


@app.command()
def apply(
    proposal_id: str = typer.Argument(..., help="ID of a pending RebalanceProposal"),
) -> None:
    """Commit a pending rebalance proposal to the fund.

    Walks the proposal's changes (new_buy/add/trim/exit/new_watch/hold),
    recomputes cash so the book stays balanced, logs the mission, and marks
    the proposal applied. No LLM calls — pure file operations.
    """
    from .fund import fund_exists
    from .proposals import apply_proposal, load_proposal
    from .ui import print_fund

    print_banner()

    if not fund_exists():
        console.print(
            '  [warn]No fund yet.[/]  Run [bold cyan]tacapes new "<thesis>"[/] first.'
        )
        raise typer.Exit(code=1)

    try:
        proposal = load_proposal(proposal_id)
    except FileNotFoundError:
        console.print(
            f"  [err]✗[/] no proposal [bold]{proposal_id}[/] on disk."
        )
        raise typer.Exit(code=1) from None

    if proposal.status != "pending":
        console.print(
            f"  [err]✗[/] proposal [bold]{proposal_id}[/] is "
            f"[bold]{proposal.status}[/], not pending — nothing to apply."
        )
        raise typer.Exit(code=1)

    fund = apply_proposal(proposal_id)
    console.print(
        f"  [ok]✓[/] applied proposal [bold]{proposal_id}[/]  ·  "
        f"[bold]{len(proposal.changes)}[/] changes committed to the book"
    )
    console.print()
    print_fund(fund)


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8732, "--port", help="Bind port"),
) -> None:
    """Launch the local web dashboard (FastAPI + HTMX on 127.0.0.1:8732)."""
    load_dotenv()
    import uvicorn

    from .dashboard.app import create_app

    print_banner()
    console.print(
        f"  [ok]dashboard[/]  ·  [bold]http://{host}:{port}[/]  "
        "[muted](Ctrl-C to stop)[/]"
    )
    console.print()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


@app.command()
def preflight() -> None:
    """Smoke-test every external dependency before a real run."""
    load_dotenv()
    failures: list[str] = []

    def _ok(label: str, detail: str = "") -> None:
        suffix = f"  [muted]{detail}[/]" if detail else ""
        console.print(f"  [ok]✓[/] {label}{suffix}")

    def _fail(label: str, detail: str) -> None:
        console.print(f"  [err]✗[/] {label}  [muted]{detail}[/]")
        failures.append(label)

    print_banner()
    console.print("[bold cyan]preflight[/]  [muted]· verify external dependencies before a real run[/]")
    console.rule(style="dim cyan")
    console.print()

    # 1. Env vars.
    missing = _missing_env_vars()
    if missing:
        _fail("env vars", f"missing: {', '.join(missing)}")
    else:
        _ok("env vars", "all 3 set")

    # 2. Anthropic.
    if "ANTHROPIC_API_KEY" not in missing:
        try:
            from langchain_anthropic import ChatAnthropic

            from .llm import DEFAULT_MODEL

            llm = ChatAnthropic(
                model=DEFAULT_MODEL,
                api_key=os.environ["ANTHROPIC_API_KEY"],
                max_tokens=5,
            )
            resp = llm.invoke("Reply with the single word: ok")
            text = (resp.content or "").strip() if hasattr(resp, "content") else str(resp)
            _ok("Anthropic", f"model={DEFAULT_MODEL}, reply={text[:30]!r}")
        except Exception as e:
            _fail("Anthropic", f"{type(e).__name__}: {e}")

    # 3. Tavily.
    if "TAVILY_API_KEY" not in missing:
        try:
            from .tools import web_search

            out = web_search.invoke({"query": "stock market today", "max_results": 1})
            if "error" in out:
                _fail("Tavily", out["error"])
            else:
                n = len(out.get("results", []))
                _ok("Tavily", f"{n} result(s)")
        except Exception as e:
            _fail("Tavily", f"{type(e).__name__}: {e}")

    # 4. NewsAPI.
    if "NEWSAPI_KEY" not in missing:
        try:
            from .tools import fetch_news

            out = fetch_news.invoke({"query": "AAPL", "days": 7, "max_items": 1})
            if "error" in out:
                _fail("NewsAPI", out["error"])
            else:
                n = len(out.get("items", []))
                _ok("NewsAPI", f"{n} item(s) in last 7d for AAPL")
        except Exception as e:
            _fail("NewsAPI", f"{type(e).__name__}: {e}")

    # 5. yfinance.
    try:
        import yfinance

        info = yfinance.Ticker("AAPL").history(period="1d", interval="1d")
        if info is None or len(info) == 0:
            _fail("yfinance", "empty history for AAPL — Yahoo may be throttling/broken")
        else:
            close = float(info["Close"].iloc[-1])
            _ok("yfinance", f"AAPL close={close:.2f}")
    except Exception as e:
        _fail("yfinance", f"{type(e).__name__}: {e}")

    console.print()
    if failures:
        console.print(
            f"[err]{len(failures)} check(s) failed:[/] {', '.join(failures)}"
        )
        raise typer.Exit(code=1)
    console.print(
        "[ok]all checks passed.[/]  Ready for [bold cyan]tacapes new ...[/]"
    )
    console.print()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
