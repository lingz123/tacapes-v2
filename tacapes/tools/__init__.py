"""LangChain-compatible tools for the M3 sub-theme researcher.

Both tools are raw `httpx` ports of the v1 implementations, decorated with
`@tool` so they work with `langgraph.prebuilt.create_react_agent`.
"""
from .news import fetch_news
from .web_search import web_search

__all__ = ["web_search", "fetch_news"]
