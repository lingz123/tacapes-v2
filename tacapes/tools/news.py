"""NewsAPI-backed news fetcher. Requires NEWSAPI_KEY in env."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from langchain_core.tools import tool

_NEWSAPI_URL = "https://newsapi.org/v2/everything"


def _fetch_news(query: str, days: int, page_size: int) -> list[dict[str, Any]]:
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        raise RuntimeError("NEWSAPI_KEY is not set")
    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    resp = httpx.get(
        _NEWSAPI_URL,
        params={
            "q": query,
            "from": since,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": min(100, page_size),
            "apiKey": api_key,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for item in resp.json().get("articles", []):
        try:
            published_at = datetime.fromisoformat(
                item["publishedAt"].replace("Z", "+00:00")
            ).isoformat()
        except (KeyError, ValueError):
            continue
        out.append({
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "source": (item.get("source") or {}).get("name") or "",
            "published_at": published_at,
            "summary": item.get("description"),
        })
    return out


@tool
def fetch_news(query: str, days: int = 30, max_items: int = 20) -> dict[str, Any]:
    """Fetch recent news articles for a query (ticker, company, or theme).

    Use for ticker- or event-specific news within a recent window. Each item
    has `url`, `title`, `source`, `published_at`, `summary`. Cite the `url`
    in your final answer's `sources` with `kind="news"`.

    Args:
        query: search query — works best with a ticker or a specific phrase.
        days: lookback window, 1..365, default 30.
        max_items: 1..100, default 20.
    """
    if not query.strip():
        return {"error": "empty query", "items": []}
    days = max(1, min(365, int(days)))
    max_items = max(1, min(100, int(max_items)))
    try:
        items = _fetch_news(query, days=days, page_size=max_items)
    except (httpx.HTTPError, RuntimeError) as e:
        return {"error": f"{type(e).__name__}: {e}", "items": []}
    return {"query": query, "days": days, "items": items}
