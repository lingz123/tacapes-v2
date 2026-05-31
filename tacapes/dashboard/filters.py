"""Jinja filters for the dashboard.

Kept in a separate module so app.py stays focused on wiring.

Two flavours:

  - color/semantic filters return a short class-name suffix
    (`good` / `warn` / `bad` / `neutral`) that pairs with the
    matching CSS classes (`.badge.conviction-good`, etc.) in
    style.css.
  - `mdtext` is a deliberately tiny markdown-ish renderer for the
    long markdown blocks stored in `TradingAgentsOutput.*_report`
    and inside driver/risk descriptions. The project avoids new
    dependencies, so this is a best-effort transform: HTML-escape,
    then `**bold**`, then collapse `# Heading` markers to bold
    lines. Whitespace is preserved by `.md-text { white-space:
    pre-wrap }` so line breaks survive without a real parser.
"""
from __future__ import annotations

import re

from markupsafe import Markup, escape


def conviction_color(conv: object) -> str:
    """1-2 → bad, 3 → warn, 4-5 → good. Anything unparseable → neutral."""
    try:
        n = int(conv)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "neutral"
    if n >= 4:
        return "good"
    if n == 3:
        return "warn"
    return "bad"


def alignment_color(align: object) -> str:
    """aligned → good, fully_diverged → bad, partial divergences → warn."""
    if align == "aligned":
        return "good"
    if align == "fully_diverged":
        return "bad"
    if isinstance(align, str) and "divergence" in align:
        return "warn"
    return "neutral"


def rating_color(rating: object) -> str:
    """PortfolioRating mapped to semantic color suffixes."""
    if rating in ("Buy", "Overweight"):
        return "good"
    if rating == "Hold":
        return "warn"
    if rating in ("Underweight", "Sell"):
        return "bad"
    return "neutral"


def severity_color(sev: object) -> str:
    return {"high": "bad", "medium": "warn", "low": "neutral"}.get(
        sev if isinstance(sev, str) else "", "neutral"
    )


def importance_color(imp: object) -> str:
    """Drivers' importance: not really good/bad, more emphasis level.
    Primary gets a 'strong' chip; the rest stay neutral."""
    return {"primary": "good", "secondary": "neutral", "tertiary": "muted"}.get(
        imp if isinstance(imp, str) else "", "neutral"
    )


def impact_color(imp: object) -> str:
    """Catalyst impact: large → warn (big upcoming move), small → muted."""
    return {"large": "warn", "medium": "neutral", "small": "muted"}.get(
        imp if isinstance(imp, str) else "", "neutral"
    )


def alignment_label(align: object) -> str:
    """Replace underscores so the badge reads naturally
    ('fully diverged' not 'fully_diverged')."""
    if not isinstance(align, str):
        return ""
    return align.replace("_", " ")


# Markdown-ish transforms. We escape first, then apply text → html replacements
# on already-escaped content. Order matters: bold before headings so we don't
# match `**` inside a `# **strong heading**` line. Headings strip the `#`
# prefix and render the rest as bold.
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def mdtext(text: object) -> Markup:
    """Best-effort markdown → HTML for analyst-report-shaped strings.

    Escapes HTML, then converts `**bold**` and `# heading` lines.
    Whitespace is preserved at the CSS layer (.md-text { white-space:
    pre-wrap }) so newlines survive without injecting `<br>`.
    """
    if not text:
        return Markup("")
    out = str(escape(text))
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _HEADING_RE.sub(r"<strong>\2</strong>", out)
    return Markup(out)


def register(env) -> None:
    """Attach all filters to a Jinja Environment.

    Called from app.create_app() so tests get the same wiring.
    """
    env.filters["conviction_color"] = conviction_color
    env.filters["alignment_color"] = alignment_color
    env.filters["alignment_label"] = alignment_label
    env.filters["rating_color"] = rating_color
    env.filters["severity_color"] = severity_color
    env.filters["importance_color"] = importance_color
    env.filters["impact_color"] = impact_color
    env.filters["mdtext"] = mdtext
