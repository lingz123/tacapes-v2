"""yfinance-backed price helpers. Two functions for entry-price snapshots:
- `snapshot_entry_price(ticker)` for missions completing now.
- `historical_entry_price(ticker, on_date)` for backfilling old missions.

Both return (price, date_used) or (None, None) on miss. Never raise on
yfinance failure — the caller persists NULL."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf  # type: ignore[import-untyped]

log = logging.getLogger(__name__)


def _first_close(df) -> Decimal | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    try:
        value = float(df["Close"].iloc[0])
    except (IndexError, ValueError, TypeError):
        return None
    return Decimal(f"{value:.4f}").normalize().quantize(Decimal("0.01"))


def snapshot_entry_price(ticker: str) -> tuple[Decimal | None, date | None]:
    """Most recent close for `ticker`. NULL on miss."""
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="5d")  # last 5 trading days
    except Exception as e:
        log.warning("yfinance snapshot failed for %s: %s", ticker, e)
        return None, None
    if df is None or df.empty:
        return None, None
    row = df.tail(1)
    price = _first_close(row)
    if price is None:
        return None, None
    date_used = row.index[0].date()
    return price, date_used


def historical_entry_price(
    ticker: str, on_date: date
) -> tuple[Decimal | None, date | None]:
    """Close on `on_date`, or the first trading day in the following 7 days
    if `on_date` was a weekend/holiday. NULL on miss."""
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(
            start=on_date.isoformat(),
            end=(on_date + timedelta(days=7)).isoformat(),
        )
    except Exception as e:
        log.warning("yfinance historical failed for %s @ %s: %s", ticker, on_date, e)
        return None, None
    if df is None or df.empty:
        return None, None
    price = _first_close(df.head(1))
    if price is None:
        return None, None
    date_used = df.index[0].date()
    return price, date_used
