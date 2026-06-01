"""One-shot importer: ~/.tacapes/portfolios/<uuid>/  ->  Postgres rows.

Called on dashboard startup IFF the missions table is empty. Idempotent:
already-imported mission ids are skipped."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from . import prices
from .db.models import Mission, MissionStatus, Position

log = logging.getLogger(__name__)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.warning("could not parse %s: %s", path, e)
        return None


def _merge_dir(directory: Path, key_field: str | None = None) -> dict:
    """Read every *.json in directory into a single dict. If `key_field` is
    given, use that field from each file's payload as the dict key; otherwise
    use the filename stem (e.g. ticker, sub_theme_id). Entries with a
    missing/None key are skipped with a warning."""
    out: dict = {}
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            continue
        if key_field is None:
            key = path.stem
        else:
            value = payload.get(key_field)
            if value is None:
                log.warning("skip %s: missing key field %r", path, key_field)
                continue
            key = value
        out[str(key)] = payload
    return out


def backfill_one_folder(session: Session, folder: Path) -> bool:
    """Backfill a single mission folder. Returns True if a row was inserted."""
    mission_payload = _read_json(folder / "mission.json")
    if mission_payload is None:
        log.warning("skip %s: no parseable mission.json", folder.name)
        return False

    try:
        mission_id = uuid.UUID(mission_payload["id"])
    except (KeyError, ValueError):
        log.warning("skip %s: invalid mission id", folder.name)
        return False

    if session.get(Mission, mission_id) is not None:
        return False  # already imported

    constraints = mission_payload.get("constraints", {})
    portfolio = _read_json(folder / "portfolio.json") or {}
    created_at = datetime.fromisoformat(mission_payload["created_at"])

    row = Mission(
        id=mission_id,
        statement=mission_payload["statement"],
        budget_usd=Decimal(str(mission_payload["budget_usd"])),
        max_positions=int(constraints.get("max_positions", 5)),
        max_position_pct=Decimal(str(constraints.get("max_position_pct", 0.4))),
        horizon_months=int(constraints.get("time_horizon_months", 12)),
        sectors_excluded=list(constraints.get("sectors_excluded", [])),
        allow_shorts=bool(constraints.get("allow_shorts", False)),
        status=MissionStatus.done,
        created_at=created_at,
        started_at=created_at,
        completed_at=created_at,
        decomposition_json=_read_json(folder / "decomposition.json"),
        assessments_json=_merge_dir(folder / "assessments"),
        shortlist_json=_read_json(folder / "shortlist.json"),
        ta_outputs_json=_merge_dir(folder / "ta_outputs"),
        memos_json=_merge_dir(folder / "memos"),
        portfolio_json=portfolio or None,
        cost_usd=None,
    )
    session.add(row)

    for p in portfolio.get("positions", []):
        ticker = p["ticker"]
        entry_price, entry_date = prices.historical_entry_price(
            ticker, on_date=created_at.date()
        )
        session.add(
            Position(
                mission_id=mission_id,
                ticker=ticker,
                weight_pct=Decimal(str(p["weight_pct"])),
                notional_usd=Decimal(str(p["notional_usd"])),
                rationale=p.get("rationale"),
                is_short=bool(p.get("is_short", False)),
                entry_price=entry_price,
                entry_price_date=entry_date,
            )
        )

    return True


def backfill_from_disk(session: Session, portfolios_root: Path) -> int:
    """Import every well-formed mission folder under `portfolios_root`.
    Returns count of newly-inserted mission rows. Each folder is wrapped in
    a SAVEPOINT so a mid-folder failure only rolls back its own partial
    inserts (not the rest of the batch)."""
    if not portfolios_root.exists():
        return 0
    inserted = 0
    for child in sorted(portfolios_root.iterdir()):
        if not child.is_dir():
            continue
        try:
            with session.begin_nested():
                if backfill_one_folder(session, child):
                    inserted += 1
        except Exception as e:  # noqa: BLE001 — a bad folder must not kill the import
            log.warning("skip %s: %s", child.name, e)
    return inserted
