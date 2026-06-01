"""yfinance is stubbed; we never hit the network in tests."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import select

from tacapes.dashboard import prices
from tacapes.dashboard.db.models import PriceQuote


def _fake_history(closes: dict[str, float]):
    """Build a `yf.Ticker` stub whose .history() returns a DataFrame with the
    given close prices keyed by ticker (caller picks one)."""
    def factory(ticker: str):
        mock = MagicMock()
        if ticker in closes:
            mock.history.return_value = pd.DataFrame(
                {"Close": [closes[ticker]]},
                index=pd.DatetimeIndex([pd.Timestamp("2026-05-30")], tz="UTC"),
            )
        else:
            mock.history.return_value = pd.DataFrame()
        return mock
    return factory


def test_snapshot_entry_price_for_today_returns_close():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 95.42})):
        price, date_used = prices.snapshot_entry_price("NRG")
    assert price == Decimal("95.42")
    assert isinstance(date_used, date)


def test_snapshot_entry_price_returns_none_on_yfinance_miss():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({})):
        price, date_used = prices.snapshot_entry_price("XXXX")
    assert price is None
    assert date_used is None


def test_historical_entry_price_finds_close_within_week():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 80.0})):
        price, date_used = prices.historical_entry_price(
            "NRG", on_date=date(2026, 5, 30)
        )
    assert price == Decimal("80.00")


def test_historical_entry_price_none_on_miss():
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({})):
        price, date_used = prices.historical_entry_price(
            "XXXX", on_date=date(2026, 5, 30)
        )
    assert price is None
    assert date_used is None


def test_get_current_prices_inserts_missing_quotes(session):
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 90.0, "CEG": 50.0})):
        out = prices.get_current_prices(session, ["NRG", "CEG"])
    assert out["NRG"] == Decimal("90.00")
    assert out["CEG"] == Decimal("50.00")
    saved = {q.ticker for q in session.scalars(select(PriceQuote))}
    assert saved == {"NRG", "CEG"}


def test_get_current_prices_returns_cached_within_window(session):
    # Pre-seed a fresh quote
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("123.00"),
        fetched_at=datetime.now(UTC) - timedelta(minutes=5),
    ))
    session.flush()
    # The fake yfinance returns a different value; cached one should win.
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 999.0})):
        out = prices.get_current_prices(session, ["NRG"])
    assert out["NRG"] == Decimal("123.00")


def test_get_current_prices_refreshes_stale_quotes(session):
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("123.00"),
        fetched_at=datetime.now(UTC) - timedelta(hours=2),
    ))
    session.flush()
    with patch.object(prices.yf, "Ticker", side_effect=_fake_history({"NRG": 200.0})):
        out = prices.get_current_prices(session, ["NRG"])
    assert out["NRG"] == Decimal("200.00")


def test_invalidate_price_cache(session):
    session.add(PriceQuote(
        ticker="NRG", price=Decimal("1.0"),
        fetched_at=datetime.now(UTC),
    ))
    session.flush()
    prices.invalidate_price_cache(session)
    session.flush()
    quote = session.get(PriceQuote, "NRG")
    assert quote is None
