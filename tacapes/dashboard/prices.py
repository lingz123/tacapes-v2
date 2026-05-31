"""yfinance-backed price helpers. Two functions for entry-price snapshots:
- `snapshot_entry_price(ticker)` for missions completing now.
- `historical_entry_price(ticker, on_date)` for backfilling old missions.

Both return (price, date_used) or (None, None) on miss. Never raise on
yfinance failure — the caller persists NULL."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import yfinance as yf  # type: ignore[import-untyped]
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db.models import PriceQuote

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=15)


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


def get_current_prices(
    session: Session, tickers: list[str]
) -> dict[str, Decimal | None]:
    """Return {ticker: current_price_or_None}. Fetches and upserts any missing
    or stale quotes. yfinance failures result in None for that ticker."""
    if not tickers:
        return {}
    cutoff = datetime.now(UTC) - CACHE_TTL
    rows = list(session.scalars(
        select(PriceQuote).where(PriceQuote.ticker.in_(tickers))
    ))
    by_ticker: dict[str, PriceQuote] = {r.ticker: r for r in rows}
    fresh: dict[str, Decimal] = {
        t: r.price for t, r in by_ticker.items() if r.fetched_at >= cutoff
    }
    stale_or_missing = [t for t in tickers if t not in fresh]

    for ticker in stale_or_missing:
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="5d")
        except Exception as e:
            log.warning("current price fetch failed for %s: %s", ticker, e)
            continue
        if df is None or df.empty:
            continue
        price = _first_close(df.tail(1))
        if price is None:
            continue
        existing = by_ticker.get(ticker)
        if existing is None:
            session.add(PriceQuote(
                ticker=ticker, price=price, fetched_at=datetime.now(UTC),
            ))
        else:
            existing.price = price
            existing.fetched_at = datetime.now(UTC)
        fresh[ticker] = price

    return {t: fresh.get(t) for t in tickers}


def invalidate_price_cache(session: Session) -> None:
    """Force the next get_current_prices to re-fetch every ticker."""
    session.execute(delete(PriceQuote))
