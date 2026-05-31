# History dashboard task log

Snapshot of the work completed on the `history-dashboard` branch, captured 2026-05-31. Use this to remember what was done if you come back to it in a few weeks.

**Spec:** `docs/superpowers/specs/2026-05-31-history-dashboard-design.md`
**Plan:** `docs/superpowers/plans/2026-05-31-history-dashboard.md`
**Branch:** `history-dashboard` (local-only, not pushed)
**Final test status:** 87 tests pass (8 pre-rewrite fund-centric tests skipped with `@pytest.mark.skip(reason="dashboard rewritten to mission-centric in branch history-dashboard")`)
**Lint status:** ruff clean
**Production smoke:** dashboard runs, renders 3 backfilled missions with current-price P&L

---

## Task completion status

| # | Phase | Task | Status | Commit |
| --- | --- | --- | --- | --- |
| 0a | spec | History dashboard design spec | ✅ done | `ec5aa2e` |
| 0b | spec | History dashboard implementation plan | ✅ done | `53edef1` |
| 1.1 | 1 | Add Python dependencies (alembic, psycopg, sqlalchemy, yfinance, pytest-postgresql) | ✅ done | `92702f6` |
| 1.2 | 1 | Docker Compose + `scripts/check-db.sh` | ✅ done | `dd91a83` → `da3b9cf` (review fix: success-msg + healthcheck start_period) |
| 1.3 | 1 | SQLAlchemy models for missions, positions, price_quotes (incl. is_short fix + max_position_pct comment) | ✅ done | `7dd473a` |
| 1.4 | 1 | Alembic config and initial schema migration (incl. enum-drop on downgrade) | ✅ done | `a9d8f14` |
| 1.5 | 1 | DB engine + session_scope + test DB fixture (TRUNCATE-after-test isolation; DROP DB WITH FORCE) | ✅ done | `c8cdd20` |
| 1.6 | 1 | Repo query helpers + 6 tests | ✅ done | `0d6b511` |
| 1.7 | 1 | `bootstrap_db` wired into `tacapes dashboard` (env check, alembic, orphan recovery) | ✅ done | `617136d` |
| 2.1 | 2 | yfinance entry-price helpers (snapshot + historical lookup, NULL on miss) | ✅ done | `1361d4c` |
| 2.2 | 2 | Portfolios → DB backfill with SAVEPOINT-per-folder isolation + idempotent skip | ✅ done | `0199c4d` |
| 2.3 | 2 | Trigger backfill on first launch when missions table empty | ✅ done | `5a923fb` |
| 3.1 | 3 | 15-min current-price cache + invalidation | ✅ done | `2d2f7ed` |
| 3.2 | 3 | Rewrite `app.py` as history-centric shell, drop 4 fund-centric templates | ✅ done | `0eef3b1` |
| 3.3 | 3 | `base.html` + `style.css` (color tokens, badges, spinner, P&L colors) | ✅ done | `cdb6300` |
| 3.4 | 3 | `GET /` history page with aggregate P&L (route + `index.html` + `_mission_row.html`) | ✅ done | `d5e9fb8` |
| 3.5 | 3 | `GET /missions/{id}` detail page, done branch (sub-theses, shortlist Chosen/Passed, reports, positions) | ✅ done | `2c97be1` |
| 3.6 | 3 | `POST /prices/refresh` cache invalidation route | ✅ done | `6943b9e` |
| 4.1 | 4 | Mission runner: pipeline → DB writes, failed-state handling | ✅ done | `073d678` |
| 4.2 | 4 | `GET /missions/new` form (all 6 CLI params + allow_shorts toggle) | ✅ done | `3b699c9` |
| 4.3 | 4 | `POST /missions` validate, enqueue, redirect to detail | ✅ done | `d1714ac` |
| 4.4 | 4 | HTMX status polling for running missions | ✅ done | `0daa8ab` |
| 5.1 | 5 | Failed-state panel (simple, no traceback, delete button) | ✅ done | `3697970` |
| 5.2 | 5 | `POST /missions/{id}/delete` (cascade + folder cleanup, 409 if running) | ✅ done | `cbbda16` |
| 5.3 | 5 | End-to-end smoke + final lint pass | ✅ done | `7f68124` |
| post | final | Fix `Job.kind` enum (add "mission") + HTMX poll fragment re-includes attrs | ✅ done | `8455cec` |
| post | final | Fix `bootstrap_db`: use `sys.executable -m alembic` to hit venv's Python 3.13 | ✅ done | `62f760f` |

Total: **28 commits**, all 23 plan tasks complete, plus 2 post-merge review fixes and 1 production smoke fix.

---

## What's actually working right now

Run with:
```bash
cd ~/tacapes-v2
docker compose up -d db
.venv/bin/tacapes dashboard            # → http://127.0.0.1:8732
```

You'll see 3 backfilled missions (Energy/Nuclear x2 from 2026-05-12, Photonics from 2026-05-11) with 12 positions and current-price P&L. The other 16 portfolio folders on disk had no parseable `mission.json` (likely crashed runs) and were skipped during backfill.

---

## Known follow-ups (not blocking, surfaced during review)

1. **Reports section is raw JSON dumps** — the memo and TA debate are rendered via `{{ memo | tojson(indent=2) }}` inside `<pre>` blocks. A follow-up task is queued to render them as styled cards (conviction badge, alignment badge, reconciliation notes panel, drivers/risks/catalysts lists, valuation table, thesis breakers callout) and the TA debate as collapsible analyst-report sections. Prompt for that work was drafted in the chat session.

2. **Sub-theses section only shows decomposition_json** — doesn't surface assessments_json (M3 researcher's key findings). Data is in the DB; the template just doesn't render it.

3. **Backfill empty-table guard** — `bootstrap_db` only runs backfill if `missions` is empty. So once the table has rows, broken folders that get a `mission.json` later won't auto-import. Easy follow-up: `tacapes backfill --force` command.

4. **Pipeline session_scope** holds a DB transaction open for the entire LangGraph run (30-60 min). Fine for single-user local; would matter at scale.

5. **8 skipped fund-centric tests** in `tests/test_dashboard.py` — kept rather than deleted so they can be revived if the fund layer ever comes back (v2.2?). They reference removed routes (`/refresh/{ticker}`, `/thesis`, `/proposal/.../apply`, `/memo/{ticker}`) and the removed `make_refresh_job`/`make_thesis_job` job builders.

---

## How review was run

Subagent-driven development: each of the 23 plan tasks got its own implementer subagent (sonnet), followed by a spec-compliance reviewer subagent and a code-quality reviewer subagent. Review issues were fixed by a follow-up subagent and amended into the same commit. A final end-to-end reviewer caught the two post-merge bugs (`Job.kind` enum and HTMX poll fragment) that the per-task reviews missed because the test scaffolding bypassed them. Production smoke caught the third bug (`alembic` PATH resolution to Anaconda Python 3.9).
