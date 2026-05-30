"""Unit tests for the M3 ReAct tools.

Patches `httpx.post`/`httpx.get` so no network is hit. Tests cover:
- happy path (Tavily + NewsAPI shapes mapped correctly)
- missing API key returns a structured error rather than raising
- malformed item dates are skipped (NewsAPI) or nulled (Tavily)
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from tacapes.tools import fetch_news, web_search


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# --- web_search ---------------------------------------------------------

def test_web_search_maps_tavily_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResponse({
            "results": [
                {
                    "title": "Vendor A wins data center deal",
                    "url": "https://example.com/a",
                    "content": "Vendor A signed a 500MW PPA with hyperscaler X.",
                    "published_date": "2026-04-15T10:00:00Z",
                },
                {
                    "title": "No date item",
                    "url": "https://example.com/b",
                    "content": "...",
                },
            ]
        })

    with patch("tacapes.tools.web_search.httpx.post", fake_post):
        out = web_search.invoke({"query": "AI data center PPAs", "max_results": 5})

    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["json"]["api_key"] == "test-key"
    assert captured["json"]["query"] == "AI data center PPAs"
    assert captured["json"]["max_results"] == 5
    assert out["query"] == "AI data center PPAs"
    assert len(out["results"]) == 2
    assert out["results"][0]["url"] == "https://example.com/a"
    assert out["results"][0]["published_at"].startswith("2026-04-15")
    assert out["results"][1]["published_at"] is None


def test_web_search_missing_key_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = web_search.invoke({"query": "anything"})
    assert "error" in out
    assert out["results"] == []


def test_web_search_empty_query_returns_error() -> None:
    out = web_search.invoke({"query": "   "})
    assert "error" in out
    assert out["results"] == []


# --- fetch_news ---------------------------------------------------------

def test_fetch_news_maps_newsapi_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSAPI_KEY", "test-key")
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return _FakeResponse({
            "articles": [
                {
                    "title": "CEG signs hyperscaler PPA",
                    "url": "https://news.example.com/1",
                    "source": {"name": "Reuters"},
                    "publishedAt": "2026-05-01T08:30:00Z",
                    "description": "summary text",
                },
                {
                    "title": "Bad date article — should be skipped",
                    "url": "https://news.example.com/2",
                    "source": {"name": "X"},
                    "publishedAt": "not-a-date",
                },
            ]
        })

    with patch("tacapes.tools.news.httpx.get", fake_get):
        out = fetch_news.invoke({"query": "CEG", "days": 60, "max_items": 10})

    assert captured["url"] == "https://newsapi.org/v2/everything"
    assert captured["params"]["q"] == "CEG"
    assert captured["params"]["pageSize"] == 10
    assert captured["params"]["apiKey"] == "test-key"
    assert out["query"] == "CEG"
    assert out["days"] == 60
    assert len(out["items"]) == 1  # the bad-date article is dropped
    assert out["items"][0]["source"] == "Reuters"
    assert out["items"][0]["url"] == "https://news.example.com/1"


def test_fetch_news_missing_key_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    out = fetch_news.invoke({"query": "anything"})
    assert "error" in out
    assert out["items"] == []


def test_fetch_news_clamps_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSAPI_KEY", "k")
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        captured["params"] = kwargs.get("params")
        return _FakeResponse({"articles": []})

    with patch("tacapes.tools.news.httpx.get", fake_get):
        fetch_news.invoke({"query": "X", "days": 9999, "max_items": 9999})

    # max_items clamped to 100, days clamped to 365.
    assert captured["params"]["pageSize"] == 100
