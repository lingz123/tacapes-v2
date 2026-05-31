# tacapes: history dashboard

Design spec. Companion to `README.md` (v2.0 one-shot pipeline) and supersedes
the dashboard portion of `claude/design_v2.md`. This document is the source of
truth for the **history dashboard** slice. It deliberately scopes *out* the
v2.1 persistent fund and incremental-thesis features; those are a later phase.

Date: 2026-05-31. Audience: implementer (you in two weeks, or any agent).

---

## 1. The problem

The v2.0 pipeline writes mission output to `~/.tacapes/portfolios/<id>/` as a
folder of JSON files and never looks at it again. There is no way to:

- See every mission you have ever run, with status and timestamps.
- Open a finished mission and walk the sub-theses, shortlist, reports, and
  position breakdown side by side.
- Know whether a given mission's recommended portfolio is currently up or down.
- Start a new run from anywhere other than the terminal.
- Delete a mission that was a misfire.

This slice fixes all five.

---

## 2. Scope decisions (locked)

- **Mission-centric.** Each mission stands alone with its own budget and its
  own portfolio. We do **not** introduce a fund layer in this slice. The v2.1
  persistent fund, incremental thesis, refresh-the-ticker, and rebalance
  proposal features are explicitly deferred.
- **Storage:** Postgres 16 in Docker, bind-mounted to `~/.tacapes/pgdata/`
  so data survives `docker rm`, `docker compose down`, and
  `docker compose down -v`.
- **UI:** FastAPI + Jinja + HTMX, extending the existing scaffold at
  `tacapes/dashboard/`.
- **In-flight missions** show a spinner and no partial state. Only completed
  missions render their stage data.
- **Price refresh** runs automatically on dashboard load with a 15-minute cache
  in Postgres. A manual button invalidates the cache.
- **Cost basis** is snapshotted from yfinance at mission completion. For
  backfilled missions, we look up the historical close on the original
  `mission.created_at` date.
- **All ~20 existing mission folders** are backfilled on first dashboard launch.
- **Failed missions** appear in history with a Failed badge. The detail page
  shows a simple "this run failed" panel. No traceback, no reason.
- **Delete** is available on the row and the detail page. It removes the DB
  rows and the on-disk folder.

---

## 3. Architecture

Two processes against one database.

```
                         ┌──────────────────────────────────┐
                         │  Docker (docker-compose)         │
                         │  ┌──────────────────────────┐    │
                         │  │ postgres:16-alpine       │    │
                         │  │ bind: ~/.tacapes/pgdata  │    │
                         │  │ 127.0.0.1:5433           │    │
                         │  └────────────▲─────────────┘    │
                         └───────────────┼──────────────────┘
                                         │ DATABASE_URL
   ┌───────────────────────────┐         │
   │  tacapes dashboard        │─────────┤
   │  (uvicorn, host process)  │         │
   │   FastAPI + Jinja + HTMX  │         │
   │   ThreadPoolExecutor(1)   │         │
   │     for mission jobs      │         │
   └───────────▲───────────────┘         │
               │                         │
               │ user clicks             │
               │ "New Mission"           │
               ▼                         │
       runs the existing                 │
       LangGraph pipeline                │
       in a worker thread,               │
       persists results to ──────────────┘
       Postgres on completion
```

**Why one DB outside the app process.** Postgres lives in Docker so data
persistence is a settled problem. The FastAPI app runs on the host so editing
templates and Python is a `uvicorn --reload` away. No container rebuild loop
during development.

**Why one worker thread.** The existing pipeline shares a process-wide
`InMemoryRateLimiter` (`tacapes/llm.py`). `ThreadPoolExecutor(max_workers=1)`
keeps the limiter shared and avoids bursting Anthropic ITPM caps. Extra
missions queue.

**Per-mission folders stay on disk.** The existing `persist` node still writes
`~/.tacapes/portfolios/<id>/` after a successful run. Going forward that is
redundant with the DB but cheap; it is the disaster-recovery source if the DB
is ever lost or corrupted.

---

## 4. Data model

Three tables. All columns NOT NULL unless noted. Postgres types in brackets.

### 4.1 `missions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | matches Pydantic `Mission.id` |
| `statement` | TEXT | the thesis |
| `budget_usd` | NUMERIC(14,2) | |
| `max_positions` | SMALLINT | |
| `max_position_pct` | NUMERIC(4,3) | 0.000–1.000 |
| `horizon_months` | SMALLINT | |
| `sectors_excluded` | TEXT[] DEFAULT '{}' | |
| `allow_shorts` | BOOLEAN DEFAULT FALSE | |
| `status` | mission_status enum | `queued`, `running`, `done`, `failed` |
| `created_at` | TIMESTAMPTZ | |
| `started_at` | TIMESTAMPTZ NULL | NULL until pipeline begins |
| `completed_at` | TIMESTAMPTZ NULL | NULL until done or failed |
| `error_message` | TEXT NULL | populated on failure, one short line |
| `decomposition_json` | JSONB NULL | M2 output (the `Decomposition` Pydantic model serialized) |
| `assessments_json` | JSONB NULL | M3 output, shape `{ "<subtheme_id>": <SubThemeAssessment>, ... }` |
| `shortlist_json` | JSONB NULL | M4 output |
| `ta_outputs_json` | JSONB NULL | shape `{ "<TICKER>": <TradingAgentsOutput>, ... }` |
| `memos_json` | JSONB NULL | shape `{ "<TICKER>": <InvestmentMemo>, ... }` |
| `portfolio_json` | JSONB NULL | M6 output (`PortfolioAllocation`) |
| `cost_usd` | NUMERIC(8,2) NULL | total LLM spend for this run |

Indexes:
- `(status, created_at DESC)` for the history list.
- `(created_at DESC)` for the all-time view.

### 4.2 `positions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `mission_id` | UUID FK → `missions(id)` ON DELETE CASCADE | |
| `ticker` | TEXT | |
| `weight_pct` | NUMERIC(5,4) | 0.0000–1.0000 |
| `notional_usd` | NUMERIC(14,2) | |
| `rationale` | TEXT NULL | |
| `entry_price` | NUMERIC(12,4) NULL | NULL on yfinance miss |
| `entry_price_date` | DATE NULL | trading day used for the snapshot |

Index: `(ticker)` for the cross-mission dedup that drives the price-refresh
fetch.

The portfolio's cash reserve is not a row. It lives in `portfolio_json` and
the UI shows it as a residual of the position weights.

### 4.3 `price_quotes`

| Column | Type | Notes |
| --- | --- | --- |
| `ticker` | TEXT PK | |
| `price` | NUMERIC(12,4) | |
| `fetched_at` | TIMESTAMPTZ | |

A 15-minute cache. Current price in the UI is always
`price_quotes.price` for a position's ticker. A missing or stale row triggers
a fetch on the next dashboard render that upserts.

### 4.4 Migrations

Alembic at `tacapes/dashboard/db/migrations/`. One initial migration creates
the three tables, the `mission_status` enum, and the indexes. The first-launch
backfill is a one-shot script (§5.5), not an alembic migration.

### 4.5 Why no separate job-state table

A mission *is* its run. `missions.status` plus `started_at`, `completed_at`,
and `error_message` cover the full lifecycle. The v2.1 design's
`jobs/<job_id>.json` was a workaround for not having a DB; with Postgres it
collapses into the missions row.

---

## 5. Data flow

### 5.1 Create a mission

```
[User] fills New Mission form on /missions/new
      │
      │ POST /missions { statement, budget, max_positions, ... }
      ▼
[FastAPI handler]
   1. validate via MissionConstraints + Mission Pydantic models
   2. INSERT missions row: status='queued', created_at=now()
   3. submit job to ThreadPoolExecutor(max_workers=1)
   4. return 303 → /missions/<id>
      │
      ▼
[Worker thread]
   1. UPDATE missions SET status='running', started_at=now()
   2. attach a CostTracker (existing) to capture cost_usd
   3. run the existing LangGraph pipeline (graph.py, unchanged)
   4. on success:
        a. snapshot entry prices via yfinance for each Position
           (Ticker.history for "today" → last close; NULL on miss)
        b. in one transaction:
            UPDATE missions SET status='done', completed_at=now(),
              cost_usd=..., decomposition_json=..., assessments_json=...,
              shortlist_json=..., ta_outputs_json=..., memos_json=...,
              portfolio_json=...
            INSERT INTO positions ... for each position
   5. on exception:
        UPDATE missions SET status='failed', completed_at=now(),
          error_message=str(exc)[:200]
        (no stage JSONB populated for a failed run)
```

`tacapes/dashboard/jobs.py` becomes the thin owner of the executor and the
DB-write callbacks. The pipeline itself does not know about Postgres. The
worker thread translates pipeline output to DB writes after `graph.invoke()`
returns.

### 5.2 Render the dashboard (`GET /`)

```
1. SELECT id, statement, status, created_at, completed_at, cost_usd
   FROM missions ORDER BY created_at DESC
2. For status='done' missions:
     SELECT mission_id, ticker, weight_pct, notional_usd, entry_price
     FROM positions WHERE mission_id = ANY(<done_ids>)
3. Collect the distinct set of tickers across all done missions.
4. SELECT ticker, price, fetched_at FROM price_quotes
   WHERE ticker = ANY(<set>)
5. Find tickers missing or stale (fetched_at < now() - 15min).
6. If any are stale: synchronously fetch from yfinance (batched), upsert
   price_quotes. Worst case one batch per dashboard load; usually zero.
7. For each done mission, compute:
      invested      = budget × (1 − cash_reserve_pct)
      current_value = Σ (notional_i / entry_price_i) × current_price_i
                      for positions with both prices present
      pnl_pct       = (current_value − invested) / invested
   Positions with NULL entry_price are excluded from current_value and
   counted in a "(N of M positions unpriced)" footnote.
8. Render history table. Running/queued rows show a spinner badge and no
   P&L cell. Failed rows show a red "Failed" badge.
```

The manual **Refresh Prices** button posts to `/prices/refresh`, which sets
`fetched_at = epoch` on every row, then redirects back. The next render hits
yfinance for everything.

### 5.3 Mission detail page (`GET /missions/<id>`)

Renders branch on `status`:

- `queued` or `running`: spinner + statement + params. No stage data. The
  spinner polls `/missions/<id>/status` every 3 seconds via HTMX; on the
  first response with a terminal status, the polling fragment emits
  `HX-Redirect: /missions/<id>` and the page reloads in the done or failed
  template.
- `failed`: simple "This mission failed." panel + statement + Delete button.
  Nothing else.
- `done`: renders, in order, from the JSONB columns:
  1. Header: statement, budget, params, cost, dates.
  2. **Sub-theses.** From `decomposition_json` joined with `assessments_json`.
  3. **Shortlist.** From `shortlist_json`. Each candidate is marked **Chosen**
     or **Passed** based on whether its ticker appears in
     `portfolio_json.positions`.
  4. **Reports.** Per-ticker TA debate and memo, accordion-collapsed, click
     to expand. From `ta_outputs_json` and `memos_json`.
  5. **Position breakdown.** Table joining `portfolio_json.positions` with
     the `positions` rows. Columns: ticker, weight%, notional, entry price,
     entry date, current price, % P&L.

### 5.4 Delete a mission

```
POST /missions/<id>/delete   (confirmation modal on the client)
  1. SELECT status FROM missions WHERE id=<id>
  2. If status='running' → 409, flash "cannot delete a running mission"
  3. DELETE FROM missions WHERE id=<id>   (positions cascade)
  4. shutil.rmtree(~/.tacapes/portfolios/<id>/, ignore_errors=True)
  5. redirect to /
```

Queued, done, and failed are all deletable. Running is the only forbidden
state.

### 5.5 First-launch backfill

On dashboard startup, if `SELECT COUNT(*) FROM missions` returns 0:

- For each `~/.tacapes/portfolios/<uuid>/`:
  - Read `mission.json` → mission row with `status='done'`,
    `created_at=mission.created_at`, `completed_at=mission.created_at`
    (the original timestamp is the best estimate we have).
  - Merge `decomposition.json`, `assessments/*.json`, `shortlist.json`,
    `ta_outputs/*.json`, `memos/*.json`, `portfolio.json` into the
    corresponding JSONB columns.
  - Insert one `positions` row per `portfolio.positions` entry.
  - For entry prices: take `mission.created_at::date`, call
    `yfinance.Ticker(t).history(start=that_date, end=that_date + 7 days)`
    and take the first available close (handles weekends and holidays).
    NULL on miss.
- Skip folders that fail to parse (likely partial or crashed runs) with a
  log line.
- Wrap the whole thing in one transaction. Partial failure rolls back; the
  next start retries cleanly.

---

## 6. Pages and routes

| Method · Path | Purpose |
| --- | --- |
| `GET /` | History page. Mission rows, header strip with aggregate cost and P&L, "New Mission" button. |
| `GET /missions/new` | Mission form. All 6 existing CLI params plus `allow_shorts`. |
| `POST /missions` | Validate, insert queued row, enqueue job, redirect to `/missions/<id>`. |
| `GET /missions/<id>` | Detail page. Branches on status per §5.3. |
| `GET /missions/<id>/status` | HTMX poll fragment. Returns the spinner partial while running; `HX-Redirect: /missions/<id>` on terminal state. |
| `POST /missions/<id>/delete` | Per §5.4. 409 if running. |
| `POST /prices/refresh` | Invalidate the 15-minute cache and redirect back. |
| `GET /healthz` | DB ping. |

Templates at `tacapes/dashboard/templates/`:
`base.html`, `index.html`, `mission_new.html`, `mission_detail.html`,
`_mission_row.html`, `_spinner.html`, `_failed.html`, `_done.html`. HTMX is
vendored at `tacapes/dashboard/static/htmx.min.js`. One small `style.css`
holds color tokens for status badges.

---

## 7. Error handling

**Pipeline crash inside the worker thread.** Caught at the worker boundary.
The handler writes `status='failed'`, `completed_at=now()`, and
`error_message=str(exc)[:200]` to the missions row. The exception is also
`logger.exception()`-ed to the uvicorn log so a developer can grep for it.
No stage JSONB columns are populated. The UI shows only the simple panel.

**yfinance failures.** Per-ticker `try/except`. On failure the position's
`entry_price` or the `price_quotes.price` stays NULL. The UI renders these
as N/A and shows the "(N of M positions unpriced)" footnote on aggregates.

**Postgres unreachable on dashboard start.** App fails fast with a clear
message instructing the user to `docker compose up -d db`. A small
`scripts/check-db.sh` wraps `pg_isready`. The first-launch backfill is
wrapped in a transaction so partial failure rolls back; retry on the next
start.

**Concurrent job submission.** The single-worker executor queues. The form
handler always returns immediately after inserting the queued row.

**Cancelling a running mission.** Out of scope. Once enqueued, a mission
runs to completion or failure. If the host process dies mid-run, a small
startup-recovery routine re-marks any `running` rows as `failed` with
`error_message='process restart'`.

**Delete during running.** Handler returns 409. The UI also disables the
button when status is `running`.

---

## 8. Testing

**Unit tests.**
- `dashboard/db/models.py`: round-trip every Pydantic stage object through
  JSONB and back.
- `dashboard/db/repo.py`: each repo function (`insert_mission`,
  `mark_running`, `mark_done`, `mark_failed`, `get_mission_with_positions`,
  `list_missions`, `delete_mission`).
- `dashboard/prices.py`: cost-basis snapshot and current-price refresh with
  a yfinance stub. Stale-cache check, batch fetch, NULL fall-back on miss.
- `dashboard/backfill.py`: backfill a fixture folder containing one done
  mission and one partial folder; assert the done one lands and the
  partial one is skipped with a log line.

**Route tests (FastAPI `TestClient`).**
- `GET /` with 0, 1, and N missions mixing statuses.
- `POST /missions` validates form, inserts row, enqueues to a synchronous
  fake `JobRunner` so the test sees `done` immediately.
- `GET /missions/<id>` for each status branch (queued, running, failed,
  done) renders the right template.
- `POST /missions/<id>/delete` cascades positions and removes the folder
  (a `tmp_path` portfolios root via env var).
- `POST /prices/refresh` invalidates the cache.
- HTMX polling endpoint returns the spinner partial while running and
  `HX-Redirect` on completion.

**Test DB fixture.** A `conftest.py` fixture either spins up a
testcontainers Postgres or uses a `tacapes_test` database on the dev
container, dropping and re-migrating per session. `DATABASE_URL` is
overridden for tests.

**No live API hits.** Tavily, NewsAPI, Anthropic, and yfinance are all
mocked. The existing `tacapes preflight` command stays as the only
live-API smoke test.

---

## 9. New dependencies

Add to `pyproject.toml`:

- `fastapi`
- `uvicorn[standard]`
- `jinja2`
- `python-multipart`
- `sqlalchemy>=2.0`
- `alembic`
- `psycopg[binary]`

Dev extras:

- `testcontainers[postgresql]` (optional; can also use a sidecar `tacapes_test` DB on the running container)

`htmx.min.js` is vendored to `tacapes/dashboard/static/`.

---

## 10. New layout

```
tacapes/
├── dashboard/
│   ├── app.py                  # FastAPI app, routes (extends existing)
│   ├── jobs.py                 # ThreadPoolExecutor(1) + DB-write callbacks
│   ├── runners.py              # pipeline-invocation glue (extends existing)
│   ├── prices.py               # yfinance snapshot + cached refresh
│   ├── backfill.py             # first-launch portfolios/ → DB import
│   ├── db/
│   │   ├── __init__.py         # engine + session factory
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── repo.py             # query helpers
│   │   └── migrations/         # alembic
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── mission_new.html
│   │   ├── mission_detail.html
│   │   ├── _mission_row.html
│   │   ├── _spinner.html
│   │   ├── _failed.html
│   │   └── _done.html
│   └── static/
│       ├── htmx.min.js
│       └── style.css
docker-compose.yml              # postgres:16-alpine + bind mount
scripts/
└── check-db.sh                 # pg_isready wrapper
```

---

## 11. Phased build plan

Each phase ships an end-to-end slice. Tests gate phase completion.

**Phase 1: Storage foundation.** `docker-compose.yml`, bind-mount setup,
SQLAlchemy + alembic skeleton, the three tables, `dashboard/db/`
modules. `tacapes dashboard` command exists and on launch confirms the DB
is reachable. No UI changes yet. Tests: DB connection, alembic up/down,
repo CRUD.

**Phase 2: Backfill.** `dashboard/backfill.py` reads every existing
`~/.tacapes/portfolios/<uuid>/` and inserts mission + positions rows on
first launch. Historical entry prices via yfinance. Tests: fixture
folder, NULL on yfinance miss, partial folder skipped, idempotent on
retry.

**Phase 3: Read-only history UI.** `GET /`, `GET /missions/<id>` (done
branch only), Jinja templates, HTMX. Header strip aggregates. Price
refresh on dashboard load with 15-min cache; manual refresh button.
Tests: `TestClient` route tests, P&L math.

**Phase 4: New mission from the UI.** `GET /missions/new`,
`POST /missions`, `tacapes/dashboard/jobs.py` with the
`ThreadPoolExecutor(1)`, worker thread that runs the existing pipeline
and persists results. `GET /missions/<id>/status` for HTMX polling. The
spinner branch of the detail page. Tests: form validation, synchronous
`JobRunner` fake, status branching.

**Phase 5: Failure and delete.** Worker `try/except` writes
`failed` + `error_message`. Failed branch of the detail page. Startup
recovery for orphaned `running` rows. Delete handler with cascade and
folder removal. Confirmation modal in UI. Tests: forced exception in
the fake pipeline, recovery on restart, delete-while-running rejected.

---

## 12. Explicitly deferred

- Persistent fund across missions, refresh-the-ticker, incremental
  thesis, rebalance proposals. (v2.1 design doc keeps the design alive
  for a future slice.)
- Live mark-to-market beyond simple cost-basis vs current-price. No
  intraday quotes; close-of-previous-trading-day only.
- Cost cap or pre-flight cost preview on the form.
- Model overrides per stage.
- Cancelling a running mission from the UI.
- Authentication. Dashboard binds to 127.0.0.1 only.
- Multi-user, multi-fund.

---

## 13. Open questions for implementation

None at spec time. The phased plan should resolve any ambiguity as it
unfolds. If something surfaces, append to this section and reference it
from the plan.
