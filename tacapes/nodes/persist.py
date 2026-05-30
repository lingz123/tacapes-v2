"""
persist (Phase 4b): write the run state to ~/.tacapes/portfolios/<mission_id>/.

Layout:
  ~/.tacapes/portfolios/<mission_id>/
    mission.json
    decomposition.json
    assessments/<sub_theme_id>.json
    shortlist.json
    ta_outputs/<TICKER>.json
    memos/<TICKER>.json
    portfolio.json
    portfolio_state.json   # PortfolioState (allocation + timestamps)

Idempotent within a single run: each invocation overwrites prior files,
so re-running with the same mission_id mutates the same directory tree.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..config import state_root
from ..schemas import PortfolioState


def _write_json(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def persist(state: dict) -> dict:
    mission = state["mission"]
    base = state_root(mission.id)
    base.mkdir(parents=True, exist_ok=True)

    _write_json(base / "mission.json", mission.model_dump_json(indent=2))

    if "decomposition" in state:
        _write_json(
            base / "decomposition.json",
            state["decomposition"].model_dump_json(indent=2),
        )

    for a in state.get("assessments", []):
        _write_json(
            base / "assessments" / f"{a.sub_theme_id}.json",
            a.model_dump_json(indent=2),
        )

    if "shortlist" in state:
        _write_json(
            base / "shortlist.json", state["shortlist"].model_dump_json(indent=2)
        )

    for o in state.get("ta_outputs", []):
        _write_json(
            base / "ta_outputs" / f"{o.ticker.upper()}.json",
            o.model_dump_json(indent=2),
        )

    for m in state.get("ta_memos", []):
        _write_json(
            base / "memos" / f"{m.ticker.upper()}.json",
            m.model_dump_json(indent=2),
        )

    if "portfolio" in state:
        portfolio = state["portfolio"]
        _write_json(base / "portfolio.json", portfolio.model_dump_json(indent=2))
        ps = PortfolioState(
            mission_id=mission.id,
            allocation=portfolio,
            created_at=datetime.now(UTC),
            last_updated=datetime.now(UTC),
        )
        _write_json(base / "portfolio_state.json", ps.model_dump_json(indent=2))

        # Cold-start (v2.1): the first run with a portfolio creates the
        # persistent fund — chosen names as `held`, passed-over memo'd names
        # as `watch` (design §6). Incremental runs (a fund already exists)
        # are a Phase 3 concern: they leave the fund untouched here and write
        # a RebalanceProposal instead.
        from ..fund import build_fund_from_run, fund_exists, save_fund  # noqa: PLC0415

        if not fund_exists():
            fund = build_fund_from_run(
                mission=mission,
                portfolio=portfolio,
                ta_memos=state.get("ta_memos") or [],
                ta_outputs=state.get("ta_outputs") or [],
            )
            save_fund(fund)

    # Incremental run (v2.1): the constructor emitted a RebalanceProposal
    # instead of a portfolio. Persist it for review — never auto-applied
    # (design §5.3). The fund itself is left untouched until `tacapes apply`.
    if "proposal" in state:
        from ..proposals import save_proposal  # noqa: PLC0415

        save_proposal(state["proposal"])

    # Markdown summary — top-level mission overview + portfolio table + cost.
    # Per-ticker notes were already written incrementally by memo_writer; this
    # builds the index and rolls up cost telemetry. Wrapped in try/except so a
    # markdown-rendering bug never loses the JSON state.
    try:
        from ..artifacts import write_summary  # noqa: PLC0415
        from ..cost import _TRACKER  # noqa: PLC0415

        snap = _TRACKER.snapshot()
        write_summary(
            mission=mission,
            decomposition=state.get("decomposition"),
            shortlist=state.get("shortlist"),
            portfolio=state.get("portfolio"),
            memos=state.get("ta_memos") or [],
            cost_breakdown=snap.breakdown(),
            elapsed_seconds=None,  # cli.py tracks the precise wall-clock
        )
    except Exception:
        pass  # purely cosmetic — JSON state above is the source of truth

    return {}  # no state mutation
