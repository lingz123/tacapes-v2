"""Backfill test: convert an on-disk portfolios/ folder tree into DB rows."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tacapes.dashboard import backfill, prices
from tacapes.dashboard.db.models import Mission, MissionStatus, Position

_FIXTURES = Path(__file__).parent / "fixtures" / "portfolios"


def _fake_historical(ticker, on_date):
    from decimal import Decimal
    from datetime import date
    return Decimal("100.00"), date(2026, 4, 1)


def test_backfill_imports_one_good_mission_skips_broken(session):
    with patch.object(prices, "historical_entry_price", side_effect=_fake_historical):
        n = backfill.backfill_from_disk(session, _FIXTURES)

    assert n == 1
    rows = session.query(Mission).all()
    assert len(rows) == 1
    assert rows[0].status == MissionStatus.done
    assert rows[0].portfolio_json["positions"][0]["ticker"] == "NRG"

    positions = session.query(Position).all()
    assert {p.ticker for p in positions} == {"NRG", "CEG"}
    for p in positions:
        assert p.entry_price is not None
        assert p.entry_price_date is not None


def test_backfill_is_no_op_on_already_present_mission(session):
    with patch.object(prices, "historical_entry_price", side_effect=_fake_historical):
        backfill.backfill_from_disk(session, _FIXTURES)
        session.commit()  # make the first batch visible to the second call's session.get()
        n_second = backfill.backfill_from_disk(session, _FIXTURES)
    assert n_second == 0  # idempotent
