"""
Shared terminal UI for tacapes-v2.

Everything visual that more than one node/CLI command touches lives here.
A single `console` instance + helpers means stage banners, spinners,
tables, and trees stay consistent across the pipeline.

Built on `rich` (already a transitive dep via langchain).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from rich.box import ROUNDED, SIMPLE_HEAD
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

_THEME = Theme({
    "ok": "bold green",
    "warn": "yellow",
    "err": "bold red",
    "stage": "bold cyan",
    "stage.sub": "italic cyan",
    "muted": "dim",
    "accent": "bold magenta",
    "ticker": "bold white",
    "rating.Buy": "bold green",
    "rating.Overweight": "green",
    "rating.Hold": "yellow",
    "rating.Underweight": "magenta",
    "rating.Sell": "bold red",
    "align.aligned": "green",
    "align.short_term_divergence": "yellow",
    "align.long_term_divergence": "yellow",
    "align.fully_diverged": "red",
})

console = Console(theme=_THEME, highlight=False)

VERSION = "0.1.0"

# Stage label → (panel title, one-line description). Keys must match
# LangGraph node names in tacapes.graph.
STAGE_INFO: dict[str, tuple[str, str]] = {
    "thesis_decomposer":
        ("M2 · thesis decomposition",
            "Decomposing the mission into mutually-exclusive sub-themes"),
    "subtheme_researcher":
        ("M3 · sub-theme research",
            "Per-theme ReAct loop · web_search (Tavily) + fetch_news (NewsAPI)"),
    "shortlist":
        ("M4 · shortlist",
            "Merging candidates across sub-themes, ranking by conviction"),
    "ta_runner":
        ("ta_runner · per-ticker TradingAgents",
            "Multi-analyst debate per ticker · slowest stage"),
    "memo_writer":
        ("memo_writer · reconciled memos",
            "Reconciling TA short-term signal against the long-term thesis"),
    "portfolio_constructor":
        ("portfolio · constructor",
            "Kelly-fractional sizing under mission constraints"),
    "persist":
        ("persist · artifacts",
            "Writing JSON state + per-ticker markdown notes to disk"),
}


# ---------- banner & framing ----------

_BANNER = r"""
████████╗ █████╗  ██████╗ █████╗ ██████╗ ███████╗███████╗
╚══██╔══╝██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝
   ██║   ███████║██║     ███████║██████╔╝█████╗  ███████╗
   ██║   ██╔══██║██║     ██╔══██║██╔═══╝ ██╔══╝  ╚════██║
   ██║   ██║  ██║╚██████╗██║  ██║██║     ███████╗███████║
   ╚═╝   ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝
"""


def print_banner() -> None:
    console.print()
    banner = Text(_BANNER, style="bold cyan", justify="left", no_wrap=True)
    subtitle = Text.assemble(
        ("  mission-driven portfolio builder", "italic cyan"),
        ("   ·   ", "dim"),
        (f"v{VERSION}", "dim"),
    )
    console.print(banner)
    console.print(subtitle)
    console.print()


def print_mission_card(mission, horizon_months: int) -> None:
    body = Table.grid(padding=(0, 2), expand=False)
    body.add_column(style="muted", no_wrap=True)
    body.add_column()
    body.add_row("mission", f"[bold]{mission.id}[/]")
    body.add_row("statement", Text(mission.statement, overflow="fold"))
    body.add_row("budget", f"[bold]${mission.budget_usd:,.2f}[/]")
    body.add_row("horizon", f"{horizon_months} months")
    body.add_row(
        "constraints",
        f"max_positions=[bold]{mission.constraints.max_positions}[/]  "
        f"max_per_pos=[bold]{mission.constraints.max_position_pct:.0%}[/]",
    )
    if mission.constraints.sectors_excluded:
        body.add_row("excluded", ", ".join(mission.constraints.sectors_excluded))

    console.print(
        Panel(
            body,
            title="[bold cyan]new mission[/]",
            title_align="left",
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1),
        )
    )
    console.print()


def stage_panel(node_name: str) -> None:
    """Print a small rounded panel marking the start of a stage."""
    label, desc = STAGE_INFO.get(node_name, (node_name, ""))
    body = Text.assemble(
        (label, "stage"),
        ("\n", ""),
        (desc, "stage.sub"),
    )
    console.print(
        Panel(
            body,
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 2),
            expand=False,
        )
    )


# ---------- per-iteration spinners (used inside nodes) ----------

@contextmanager
def working(message: str, spinner: str = "dots") -> Iterator[None]:
    """Context manager: spinner with message while a long op runs.

    Usage:
        with working(f"[{i}/{n}] {ticker} · TradingAgents debate..."):
            out = ta.propagate(ticker, today)
        console.print("  [ok]✓[/] ...")  # persistent line after
    """
    with console.status(f"[stage.sub]{message}[/]", spinner=spinner):
        yield


def ok_line(message: str, cost_tag: str = "") -> None:
    suffix = f"  [muted]{cost_tag}[/]" if cost_tag else ""
    console.print(f"  [ok]✓[/] {message}{suffix}")


def fail_line(message: str) -> None:
    console.print(f"  [err]✗[/] {message}")


def skipped_line(message: str, cost_tag: str = "") -> None:
    suffix = f"  [muted]{cost_tag}[/]" if cost_tag else ""
    console.print(f"  [warn]·[/] {message}{suffix}")


def cost_tag(stage_cost: float, models: list[str]) -> str:
    """Format the per-stage cost label that appears after ok_line()."""
    if stage_cost <= 0 and not models:
        return ""
    model_str = "+".join(models) if models else "untracked"
    return f"${stage_cost:.2f} · {model_str}"


# ---------- rich data renderers (called from cli.py) ----------

def print_subtheme_tree(decomposition) -> None:
    """Tree view: sub-theme branches with hypothesis + drivers + risks nested."""
    tree = Tree(
        "[stage]sub-themes[/]",
        guide_style="cyan",
    )
    for st in decomposition.sub_themes:
        branch = tree.add(
            Text.assemble(
                (f"{st.id}", "bold cyan"),
                ("  ", ""),
                (st.name, "white"),
                ("  ", ""),
                (f"conf={st.confidence:.2f}", "muted"),
            )
        )
        branch.add(Text(f"hypothesis: {st.hypothesis}", style="italic"))
        if st.growth_drivers:
            drivers = branch.add("[muted]growth drivers[/]")
            for d in st.growth_drivers:
                drivers.add(Text(d, style="green"))
        if st.risks:
            risks = branch.add("[muted]risks[/]")
            for r in st.risks:
                risks.add(Text(r, style="yellow"))
    console.print(tree)


def print_shortlist_table(shortlist) -> None:
    table = Table(
        box=SIMPLE_HEAD,
        title="[stage]shortlist[/]",
        title_justify="left",
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("#", style="muted", justify="right", no_wrap=True)
    table.add_column("Ticker", style="ticker", no_wrap=True)
    table.add_column("Sub-themes", style="cyan")
    table.add_column("Why relevant", overflow="fold")
    for i, c in enumerate(shortlist.candidates, 1):
        table.add_row(
            str(i),
            c.ticker,
            ", ".join(c.sub_theme_ids),
            c.why_relevant,
        )
    console.print(table)


def print_portfolio_table(portfolio, memos: list) -> None:
    memos_by_ticker = {m.ticker.upper(): m for m in memos}
    table = Table(
        box=ROUNDED,
        title=f"[stage]portfolio[/]  [muted]·  {portfolio.mission_id}[/]",
        title_justify="left",
        show_lines=False,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Ticker", style="ticker", no_wrap=True)
    table.add_column("Weight", justify="right")
    table.add_column("Notional", justify="right")
    table.add_column("Conv", justify="center")
    table.add_column("Alignment", justify="left")
    table.add_column("Rationale", overflow="fold")

    for p in portfolio.positions:
        memo = memos_by_ticker.get(p.ticker.upper())
        conv = f"{memo.conviction}/5" if memo else "—"
        align = memo.thesis_alignment if memo else "—"
        align_styled = f"[align.{align}]{align}[/]" if memo else "—"
        table.add_row(
            p.ticker,
            f"[bold]{p.weight_pct*100:.2f}%[/]",
            f"${p.notional_usd:,.2f}",
            conv,
            align_styled,
            p.rationale[:80] + ("…" if len(p.rationale) > 80 else ""),
        )
    cash_notional = portfolio.total_budget_usd * portfolio.cash_reserve_pct
    table.add_row(
        "[muted]cash[/]",
        f"[muted]{portfolio.cash_reserve_pct*100:.2f}%[/]",
        f"[muted]${cash_notional:,.2f}[/]",
        "[muted]—[/]", "[muted]—[/]", "[muted]reserve[/]",
    )
    console.print(table)


def _conviction_cell(conviction: int) -> str:
    """Conviction badge — green high, yellow neutral, red low."""
    style = "ok" if conviction >= 4 else ("warn" if conviction == 3 else "err")
    return f"[{style}]●{conviction}[/]"


def _holdings_table(holdings: list, title: str, *, show_weight: bool) -> Table:
    table = Table(
        box=SIMPLE_HEAD,
        title=f"[stage]{title}[/]",
        title_justify="left",
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("Ticker", style="ticker", no_wrap=True)
    table.add_column("Weight", justify="right")
    table.add_column("Conv", justify="center")
    table.add_column("TA-Rating", justify="left")
    table.add_column("Alignment", justify="left")
    table.add_column("Refreshed", justify="left", style="muted", no_wrap=True)
    table.add_column("Thesis", overflow="fold")
    for h in sorted(holdings, key=lambda x: (-x.weight_pct, -x.conviction)):
        weight = f"[bold]{h.weight_pct*100:.1f}%[/]" if show_weight else "[muted]—[/]"
        table.add_row(
            h.ticker,
            weight,
            _conviction_cell(h.conviction),
            f"[rating.{h.ta_rating}]{h.ta_rating}[/]",
            f"[align.{h.thesis_alignment}]{h.thesis_alignment}[/]",
            h.last_refreshed.date().isoformat(),
            h.thesis_one_liner,
        )
    return table


def print_fund(fund) -> None:
    """Render the persistent book: header card + held + watchlist tables."""
    held = [h for h in fund.holdings if h.status == "held"]
    watch = [h for h in fund.holdings if h.status == "watch"]
    held_weight = sum(h.weight_pct for h in held)
    cash_pct = fund.cash_usd / fund.nav_usd if fund.nav_usd else 0.0

    body = Table.grid(padding=(0, 2), expand=False)
    body.add_column(style="muted", no_wrap=True)
    body.add_column()
    body.add_row("NAV", f"[bold]${fund.nav_usd:,.2f}[/]")
    body.add_row(
        "cash",
        f"[bold]${fund.cash_usd:,.2f}[/]  [muted]({cash_pct*100:.1f}% · "
        f"invested {held_weight*100:.1f}%)[/]",
    )
    body.add_row("holdings", f"[bold]{len(held)}[/] held  ·  [bold]{len(watch)}[/] watch")
    body.add_row("missions", f"[bold]{len(fund.mission_log)}[/] applied")
    body.add_row("updated", fund.updated_at.isoformat(timespec="seconds"))
    console.print(
        Panel(
            body,
            title="[bold cyan]fund · the book[/]",
            title_align="left",
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1),
        )
    )
    console.print()

    if held:
        console.print(_holdings_table(held, "HELD", show_weight=True))
        console.print()
    if watch:
        console.print(_holdings_table(watch, "WATCHLIST", show_weight=False))
        console.print()
    if not fund.holdings:
        console.print("  [muted](no holdings yet)[/]")
        console.print()


# action → display style for a rebalance proposal
_ACTION_STYLE: dict[str, str] = {
    "new_buy": "ok",
    "add": "ok",
    "hold": "muted",
    "trim": "warn",
    "exit": "err",
    "new_watch": "stage.sub",
}


def print_proposal(proposal) -> None:
    """Render a RebalanceProposal: header card + per-ticker changes table."""
    body = Table.grid(padding=(0, 2), expand=False)
    body.add_column(style="muted", no_wrap=True)
    body.add_column()
    body.add_row("proposal", f"[bold]{proposal.id}[/]")
    body.add_row("status", f"[bold]{proposal.status}[/]")
    body.add_row("cash after", f"[bold]{proposal.cash_after_pct*100:.1f}%[/] of NAV")
    body.add_row("changes", f"[bold]{len(proposal.changes)}[/]")
    body.add_row("summary", Text(proposal.summary, overflow="fold"))
    console.print(
        Panel(
            body,
            title="[bold cyan]rebalance proposal[/]",
            title_align="left",
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1),
        )
    )
    console.print()

    table = Table(
        box=SIMPLE_HEAD,
        title="[stage]proposed changes[/]",
        title_justify="left",
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("Ticker", style="ticker", no_wrap=True)
    table.add_column("Action", no_wrap=True)
    table.add_column("Current", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Conv", justify="center")
    table.add_column("Rationale", overflow="fold")
    order = {"new_buy": 0, "add": 1, "hold": 2, "trim": 3, "exit": 4, "new_watch": 5}
    for c in sorted(proposal.changes, key=lambda x: order.get(x.action, 9)):
        style = _ACTION_STYLE.get(c.action, "muted")
        table.add_row(
            c.ticker,
            f"[{style}]{c.action}[/]",
            f"{c.current_weight_pct*100:.1f}%",
            f"[bold]{c.target_weight_pct*100:.1f}%[/]",
            _conviction_cell(c.conviction),
            c.rationale,
        )
    console.print(table)
    console.print()


def print_cost_table(snap, elapsed_seconds: float) -> None:
    mins, secs = divmod(int(elapsed_seconds), 60)
    table = Table(
        box=ROUNDED,
        title="[stage]cost & timing[/]",
        title_justify="left",
        show_lines=False,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Model", no_wrap=True)
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("USD", justify="right", style="bold")

    rows = snap.breakdown()
    if not rows:
        table.add_row("[muted](no tracked LLM usage)[/]", "—", "—", "—")
    else:
        for model, in_tok, out_tok, usd in rows:
            table.add_row(model, f"{in_tok:,}", f"{out_tok:,}", f"${usd:.2f}")
    table.add_row(
        "[bold]TOTAL[/]", "", "",
        f"[bold accent]${snap.total_usd():.2f}[/]",
    )

    elapsed_panel = Panel(
        Text.assemble(
            ("elapsed  ", "muted"),
            (f"{mins}m {secs}s", "bold"),
        ),
        box=ROUNDED,
        border_style="cyan",
        padding=(0, 2),
        expand=False,
    )

    console.print(table)
    console.print(elapsed_panel)


def print_artifacts_path(notes_dir, n_ticker_notes: int, has_summary: bool) -> None:
    body = Table.grid(padding=(0, 2))
    body.add_column(style="muted", no_wrap=True)
    body.add_column()
    body.add_row("path", f"[bold]{notes_dir}[/]")
    if has_summary:
        body.add_row("•", "[bold]_SUMMARY.md[/]  [muted](mission overview)[/]")
    body.add_row(
        "•",
        f"[bold]{n_ticker_notes}[/] per-ticker notes  "
        f"[muted](TICKER.md · pre-eval, TA debate, reconciled memo)[/]",
    )
    console.print(
        Panel(
            body,
            title="[bold cyan]artifacts[/]",
            title_align="left",
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1),
        )
    )


# ---------- timing helper ----------

def fmt_elapsed(t0: float) -> str:
    elapsed = time.monotonic() - t0
    if elapsed < 60:
        return f"{elapsed:.0f}s"
    m, s = divmod(int(elapsed), 60)
    return f"{m}m {s}s"
