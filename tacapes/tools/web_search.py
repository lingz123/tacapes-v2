"""Tavily-backed web search tool. Requires TAVILY_API_KEY in env."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx
from langchain_core.tools import tool

_TAVILY_URL = "https://api.tavily.com/search"


def _tavily_search(query: str, max_results: int) -> list[dict[str, Any]]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    resp = httpx.post(
        _TAVILY_URL,
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for item in resp.json().get("results", []):
        published_at: str | None = None
        raw_pub = item.get("published_date")
        if raw_pub:
            try:
                published_at = datetime.fromisoformat(
                    raw_pub.replace("Z", "+00:00")
                ).isoformat()
            except ValueError:
                published_at = None
        out.append({
            "title": (item.get("title") or "")[:300],
            "url": item.get("url") or "",
            "snippet": (item.get("content") or "")[:1000],
            "published_at": published_at,
        })
    return out


@tool
def web_search(query: str, max_results: int = 8) -> dict[str, Any]:
    """Search the public web via Tavily.

    Use for recent events, vendor announcements, industry context, analyst
    blogs, government/regulatory pages — anything that isn't ticker-specific
    news. Each result has `url`, `title`, `snippet`, and (best-effort)
    `published_at`. Cite the `url` in your final answer's `sources`.

    Args:
        query: search query (free text).
        max_results: 1..20, default 8.
    """
    if not query.strip():
        return {"error": "empty query", "results": []}
    max_results = max(1, min(20, int(max_results)))
    try:
        results = _tavily_search(query, max_results=max_results)
    except (httpx.HTTPError, RuntimeError) as e:
        return {"error": f"{type(e).__name__}: {e}", "results": []}
    return {
        "query": query,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "results": results,
    }
