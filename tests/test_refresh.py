"""
Phase 2 tests — the refresh operation.

`refresh_ticker` is exercised through its injectable seams: a mock `propagate`
(no real TradingAgents debate) and a mock `write_memo` (no real LLM). The
on-disk lineage — mission.json, decomposition.json, assessments/, memos/ — is
produced by running the mocked cold-start graph from test_fund.py, so the
refresh reloads real thesis context from a real (tmp) mission folder.

Covered: prior-memo archiving into memos/history/, the fresh memo overwriting
memos/<TICKER>.json, thesis-context reload, None-subtheme tolerance, the
no-prior-memo path, and the fund write-back (refresh_holding).
"""
from __future__ import annotations

from datetime import UTC, datetime

from tacapes.config import state_root
from tacapes.fund import get_holding, refresh_holding
from tacapes.refresh import refresh_ticker
from tacapes.schemas import Holding, InvestmentMemo

from tests.test_fund import run_cold_start


# ---------------------------------------------------------------------------
# injectable mock seams
# ---------------------------------------------------------------------------

def _mock_propagate(rating: str):
    """A propagate seam that returns a canned ta_output with a chosen rating."""
    def fn(cand, mission_id):
        from tacapes.nodes.ta_runner import _mock_output
        return _mock_output(cand, mission_id).model_copy(update={"rating": rating})
    return fn


def _mock_write_memo(capture: dict | None = None):
    """A write_memo seam backed by the deterministic mock memo builder.
    Records the thesis context it received into `capture` if provided."""
    def fn(*, ta_out, sub_theme, assessment, mission_horizon_months, llm):
        from tacapes.nodes.memo_writer import _mock_one
        if capture is not None:
            capture["sub_theme"] = sub_theme
            capture["assessment"] = assessment
            capture["horizon"] = mission_horizon_months
        return _mock_one(ta_out), "full"
    return fn


# ---------------------------------------------------------------------------
# refresh_ticker — archiving + memo rewrite
# ---------------------------------------------------------------------------

def test_refresh_archives_prior_memo_and_rewrites(tmp_path, monkeypatch) -> None:
    m, fund = run_cold_start(tmp_path, monkeypatch)
    holding = get_holding(fund, "NUSC")
    assert holding.conviction == 5  # cold start: mock Buy + aligned → 5

    mission_dir = state_root(m.id)
    memo_path = mission_dir / "memos" / "NUSC.json"
    prior = InvestmentMemo.model_validate_json(memo_path.read_text())
    assert prior.conviction == 5

    # Refresh with a Sell rating → mock memo conviction MATRIX[Sell, aligned] = 1.
    result = refresh_ticker(
        holding,
        propagate=_mock_propagate("Sell"),
        write_memo=_mock_write_memo(),
    )

    assert result.ticker == "NUSC"
    assert result.ta_rating == "Sell"
    assert result.prior_conviction == 5
    assert result.new_conviction == 1

    # The prior memo was archived verbatim under memos/history/.
    history_dir = mission_dir / "memos" / "history"
    archived = list(history_dir.glob("NUSC.*.json"))
    assert len(archived) == 1
    assert result.history_ref == f"memos/history/{archived[0].name}"
    assert InvestmentMemo.model_validate_json(archived[0].read_text()).conviction == 5

    # The live memo file now holds the fresh (downgraded) memo.
    fresh = InvestmentMemo.model_validate_json(memo_path.read_text())
    assert fresh.conviction == 1

    # ta_outputs/<TICKER>.json is overwritten so the memo's ta_output_ref
    # stays honest — it must reflect the fresh (Sell) debate, not the cold start.
    from tacapes.schemas import TradingAgentsOutput
    ta_path = mission_dir / "ta_outputs" / "NUSC.json"
    assert TradingAgentsOutput.model_validate_json(ta_path.read_text()).rating == "Sell"

    # The per-ticker note was rewritten (design §5.1 step 5).
    note = (mission_dir / "notes" / "NUSC.md").read_text()
    assert "Final conviction:** **1/5" in note


def test_refresh_reloads_thesis_context(tmp_path, monkeypatch) -> None:
    """The refresh reloads SubTheme + SubThemeAssessment from the source
    mission folder using only the Holding's stored lineage."""
    m, fund = run_cold_start(tmp_path, monkeypatch)
    holding = get_holding(fund, "NUSC")
    assert holding.subtheme_id == "smr"

    capture: dict = {}
    refresh_ticker(
        holding,
        propagate=_mock_propagate("Buy"),
        write_memo=_mock_write_memo(capture),
    )

    assert capture["sub_theme"] is not None
    assert capture["sub_theme"].id == "smr"
    assert capture["assessment"] is not None
    assert capture["assessment"].sub_theme_id == "smr"
    assert capture["horizon"] == 12  # from the source mission's constraints


def test_refresh_tolerates_missing_subtheme(tmp_path, monkeypatch) -> None:
    """memo_writer tolerates sub_theme=None — a Holding with no subtheme_id
    must still refresh cleanly."""
    m, _fund = run_cold_start(tmp_path, monkeypatch)
    now = datetime.now(UTC)
    holding = Holding(
        ticker="NUSC",
        status="held",
        weight_pct=0.25,
        notional_usd=5_000.0,
        conviction=3,
        ta_rating="Hold",
        thesis_alignment="aligned",
        thesis_one_liner="cross-theme name",
        note="surfaced cross-theme",
        source_mission_id=m.id,
        subtheme_id=None,  # no lineage to a sub-theme
        memo_ref=f"portfolios/{m.id}/memos/NUSC.json",
        added_at=now,
        last_refreshed=now,
    )

    capture: dict = {}
    result = refresh_ticker(
        holding,
        propagate=_mock_propagate("Buy"),
        write_memo=_mock_write_memo(capture),
    )

    assert capture["sub_theme"] is None
    assert capture["assessment"] is None
    assert result.new_conviction == 5  # Buy + aligned


def test_refresh_handles_no_prior_memo(tmp_path, monkeypatch) -> None:
    """Refreshing a holding whose memo file does not yet exist still writes a
    fresh memo and reports the absence of an archive."""
    m, _fund = run_cold_start(tmp_path, monkeypatch)
    now = datetime.now(UTC)
    holding = Holding(
        ticker="ZZZ",
        status="watch",
        conviction=3,
        ta_rating="Hold",
        thesis_alignment="aligned",
        thesis_one_liner="brand new name",
        note="newly added watch",
        source_mission_id=m.id,
        subtheme_id="smr",
        memo_ref=f"portfolios/{m.id}/memos/ZZZ.json",
        added_at=now,
        last_refreshed=now,
    )

    result = refresh_ticker(
        holding,
        propagate=_mock_propagate("Overweight"),
        write_memo=_mock_write_memo(),
    )

    assert result.history_ref == "(no prior memo)"
    memo_path = state_root(m.id) / "memos" / "ZZZ.json"
    assert memo_path.exists()
    assert InvestmentMemo.model_validate_json(memo_path.read_text()).conviction == 4


# ---------------------------------------------------------------------------
# refresh_holding — fund write-back
# ---------------------------------------------------------------------------

def test_refresh_holding_updates_signals_not_weights(tmp_path, monkeypatch) -> None:
    m, fund = run_cold_start(tmp_path, monkeypatch)
    holding = get_holding(fund, "NUSC")
    prior_weight = holding.weight_pct
    prior_notional = holding.notional_usd
    assert holding.conviction == 5

    result = refresh_ticker(
        holding,
        propagate=_mock_propagate("Sell"),
        write_memo=_mock_write_memo(),
    )
    updated = refresh_holding(
        fund, ticker="NUSC", memo=result.memo, ta_rating=result.ta_rating,
    )

    # health signals refreshed
    assert updated.conviction == 1
    assert updated.ta_rating == "Sell"
    assert updated.thesis_alignment == "aligned"
    # a refresh reports, it does not trade — weight/notional untouched
    assert updated.weight_pct == prior_weight
    assert updated.notional_usd == prior_notional
    # the fund holds exactly one NUSC line, with the new conviction
    assert get_holding(fund, "NUSC").conviction == 1
    assert sum(1 for h in fund.holdings if h.ticker == "NUSC") == 1


def test_refresh_holding_keeps_fund_invariant(tmp_path, monkeypatch) -> None:
    """A refresh must not break the held-weights + cash == NAV invariant."""
    m, fund = run_cold_start(tmp_path, monkeypatch)
    holding = get_holding(fund, "CEG")

    result = refresh_ticker(
        holding,
        propagate=_mock_propagate("Underweight"),
        write_memo=_mock_write_memo(),
    )
    refresh_holding(fund, ticker="CEG", memo=result.memo, ta_rating=result.ta_rating)

    # Re-validating the mutated fund must still pass the model validator.
    from tacapes.schemas import Fund
    Fund.model_validate(fund.model_dump())


def test_refresh_works_identically_for_watch_holdings(tmp_path, monkeypatch) -> None:
    """Design §5.1 — refresh works identically for held and watch holdings; a
    watch holding stays a watchlist line (status + zero weight) after refresh."""
    from tacapes.schemas import Fund

    m, _fund = run_cold_start(tmp_path, monkeypatch)
    now = datetime.now(UTC)
    watch = Holding(
        ticker="NUSC",  # on-disk artifacts exist for NUSC
        status="watch",
        conviction=3,
        ta_rating="Hold",
        thesis_alignment="aligned",
        thesis_one_liner="watched name",
        note="passed over at construction",
        source_mission_id=m.id,
        subtheme_id="smr",
        memo_ref=f"portfolios/{m.id}/memos/NUSC.json",
        added_at=now,
        last_refreshed=now,
    )
    fund = Fund(
        nav_usd=20_000.0, cash_usd=20_000.0, holdings=[watch], mission_log=[],
        created_at=now, updated_at=now,
    )

    result = refresh_ticker(
        watch, propagate=_mock_propagate("Buy"), write_memo=_mock_write_memo(),
    )
    updated = refresh_holding(
        fund, ticker="NUSC", memo=result.memo, ta_rating=result.ta_rating,
    )

    assert updated.status == "watch"        # still a watchlist line
    assert updated.weight_pct == 0.0        # never trades
    assert updated.notional_usd == 0.0
    assert updated.conviction == 5          # Buy + aligned — signals refreshed
    assert updated.ta_rating == "Buy"
