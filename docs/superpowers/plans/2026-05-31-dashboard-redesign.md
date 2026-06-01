# tacapes: dashboard redesign — phased plan

Companion to `docs/superpowers/specs/2026-05-31-dashboard-redesign-design.md`.
That spec is the source of truth for **what** we're building; this plan is
the day-by-day **how** and **when**.

Date authored: 2026-05-31. Estimated execution window: **7-10 working days**
(see §10 risk budget). Branch: cut `dashboard-redesign` from current HEAD.

---

## 0. Goal

Replace the Jinja+HTMX dashboard with a React + shadcn/ui SPA against a
JSON API on FastAPI, while landing the P0 + P1 improvements from the
design crit:

- **P0:** cross-linked narrative (positions ↔ memos ↔ sub-themes ↔
  shortlist), scan-first reorder (Outcome zone on top), stat strip in
  detail header, sub-themes × assessments × portfolio join.
- **P1:** weak-spot signals (fallback / momentum-trap / losing position)
  surfaced in memo summary rows, memo writer fallback badge promoted from
  bottom to summary, TA debate reordered debate-chronologically with
  markdown headings rendered as block elements.

Out of scope (Sprint 2): per-ticker drill page, sticky ticker nav,
header-level delete, raw notes link, dark mode toggle, em-dash fix
upstream.

---

## 1. Pre-conditions

Before Phase 1 starts:

- [ ] Sprint 1 spec read and locked decisions confirmed.
- [ ] `pnpm` available locally (or substitute `npm` consistently).
- [ ] Node 20+ available locally.
- [ ] Dashboard runs cleanly on `history-dashboard` (verified: 88 tests pass, dashboard up at :8732).
- [ ] Branch `dashboard-redesign` cut from current HEAD.

---

## 2. Phase 1 · Scaffold (~1 day)

**Goal.** Empty React app shell, served by FastAPI in prod, served by
Vite in dev, with Tailwind + shadcn ready to receive components.

### Build order

1. Scaffold the Vite project under `tacapes/dashboard/web/`:
   ```
   pnpm create vite@latest tacapes/dashboard/web -- --template react-ts
   cd tacapes/dashboard/web && pnpm install
   ```
2. Install Tailwind + autoprefixer + postcss, initialize config, point at `src/**/*.{ts,tsx}`.
3. Install shadcn/ui scaffolding: `pnpm dlx shadcn@latest init` with neutral palette, CSS variables on.
4. Add the design tokens (spec §6) to `src/styles/tokens.css`; mirror in `tailwind.config.ts`.
5. Install fonts: `@fontsource-variable/inter` and `@fontsource-variable/jetbrains-mono`, import in `src/main.tsx`.
6. Set up React Router with `/` and `/missions/:id` route stubs returning placeholder pages.
7. Set up TanStack Query client + provider in `src/main.tsx`.
8. Configure `vite.config.ts` with a dev-only `/api` proxy to `http://127.0.0.1:8732`.
9. In `tacapes/dashboard/app.py`, add a production-only branch that mounts `web/dist/` as static and serves `index.html` on unmatched routes. (Dev branch keeps the existing Jinja routes alive.)
10. Add `pnpm` scripts: `dev`, `build`, `test`, `lint`, `typecheck`.

### Deliverables

- `tacapes/dashboard/web/` with React app loading `/` and `/missions/:id` with a "TODO" placeholder.
- `vite dev` runs at :5173, hits `/api/healthz` through the proxy, gets `{ok:true}`.
- `pnpm build` produces `web/dist/`; `uvicorn` serves it at :8732.
- One commit: `Scaffold React + shadcn dashboard SPA`.

### Tests for the gate

- `pnpm build` exits 0.
- `pnpm test` exits 0 (vitest installed, zero tests).
- `pytest tests/dashboard -q` unchanged: 88 pass.

---

## 3. Phase 2 · JSON API surface (~1 day)

**Goal.** All seven `/api/*` endpoints exist with Pydantic response
models and JSON-shape tests. Existing HTML routes untouched.

### Build order

1. Create `tacapes/dashboard/api/` package: `__init__.py`, `routes.py`, `schemas.py`.
2. Define response models in `api/schemas.py`:
   - `MissionListItem`, `AggregateStats`, `MissionListResponse`
   - `MissionDetail`, `StatStrip`, `SubthemeSummary`, `WeakSpot`
   - `MissionStatusResponse`
3. Implement endpoints in `api/routes.py`. Reuse `repo.py` query helpers verbatim where possible. Compute `stat_strip` and `subtheme_summary` and `weak_spots` at the API boundary (TypeScript shouldn't recompute portfolio math).
4. Register the router in `app.py` after the existing route module (`api/routes.register(app)`).
5. Add `tests/dashboard/test_api.py`:
   - Each endpoint returns expected shape against backfilled fixtures.
   - `POST /api/missions` validates and enqueues using the existing `_SyncJobRunner` fake.
   - `DELETE /api/missions/:id` cascades and returns 409 when running.
   - `GET /api/missions/:id/status` returns the correct status string.
   - The `stat_strip`, `subtheme_summary`, and `weak_spots` derivations are correct (one test per derivation).

### Deliverables

- ~7 endpoints live, ~12 new tests passing.
- `MissionDetail.weak_spots` correctly identifies fallback memos, momentum traps (conviction == 3 AND `thesis_alignment != 'aligned'`), and losing positions (current_pnl_pct < 0).
- One commit: `Add JSON API alongside Jinja routes`.

### Tests for the gate

- New `tests/dashboard/test_api.py` green.
- Existing tests still green.
- `curl :8732/api/missions | jq` shows real data from the 3 backfilled missions.

---

## 4. Phase 3 · Design system + app shell (~1 day)

**Goal.** Token foundation locked, shadcn primitives copied in, TopBar +
layout chrome rendered.

### Build order

1. Run `pnpm dlx shadcn@latest add` for: `button`, `badge`, `card`, `table`, `tabs`, `accordion`, `separator`, `tooltip`, `dialog`, `skeleton`, `sonner`, `scroll-area`, `input`, `label`, `select`, `textarea`, `form`. All land in `web/src/components/ui/`.
2. Build `<TopBar>` and the app shell layout: brand link, `+ New mission` button (placeholder), refresh-prices button (placeholder).
3. Establish typography rules in `globals.css`: body Inter 14px, mono JetBrains Mono, heading scale.
4. Build the custom semantic-badge wrappers: `<ConvictionBadge>`, `<AlignmentBadge>`, `<RatingBadge>`, `<PnlPill>`. Pure functions of input; tested in isolation.
5. Build `<StatStrip>` as a flex of 4-6 `<Card>`s with label + value + optional delta indicator.
6. Add `web/src/lib/format.ts` with `usd()`, `pct()`, `relativeDate()`, and `web/src/lib/derive.ts` with `convictionColor()`, `alignmentColor()`, `ratingColor()`, `pnlColor()` (TS ports of the Jinja filters).

### Deliverables

- TopBar visible on both placeholder routes.
- A `/styleguide` route (dev-only, removed before Sprint 1 close) showing every badge, pill, and stat tile against sample data.
- One commit: `Adopt shadcn primitives + custom badge components`.

### Tests for the gate

- `pnpm test` covers each badge wrapper: input → expected `data-variant` attribute.
- `<StatStrip>` renders all six tiles given a full input; degrades to fewer when fields are null.

---

## 5. Phase 4 · Mission list page (~1.5 days)

**Goal.** `/` route fully built against `/api/missions`, including the
new-mission Dialog.

### Build order

1. `web/src/api/missions.ts` — TanStack Query hooks: `useMissionList()`, `useCreateMission()`, `useDeleteMission()`, `useRefreshPrices()`.
2. `<MissionRow>` component: status badge, statement (line-clamp 2), created date, cost, P&L pill, ⋯ menu (with Delete that opens a confirm Dialog).
3. `<MissionListPage>`: header with `<StatStrip>` for aggregate stats, action bar with `+ New mission` and `Refresh prices`, `<Table>` of `<MissionRow>`s.
4. `<NewMissionDialog>`: shadcn `<Dialog>` + react-hook-form + zod schema mirroring `MissionConstraints`. Submits via `useCreateMission()`, on success navigates to `/missions/:id`.
5. Add `<EmptyState>` for the no-missions case.
6. `<MissionListPage>` tests with MSW stubs: empty list, three missions, create flow, delete flow, refresh-prices flow, validation errors.

### Deliverables

- `/` renders the three backfilled missions with correct P&L pills.
- `+ New mission` opens a Dialog, submits, redirects to detail.
- Delete from the ⋯ menu shows a confirm Dialog, removes the row, toasts.
- One commit: `Build mission list page in React`.

### Tests for the gate

- ~6 Vitest cases on `<MissionListPage>` green.
- Dogfood: `/` in the browser at :5173 looks correct against live backend.

---

## 6. Phase 5 · Mission detail page (~2 days)

**Goal.** The big one. New IA, full P0 + P1 implementation.

### Build order

**Day 1 of the phase (chrome + outcome zone):**

1. `web/src/api/mission.ts` — `useMissionDetail(id)`, `useMissionStatus(id)` with 3s polling while not terminal.
2. `<MissionDetailPage>` shell with status branching: queued/running → skeleton + spinner, failed → simple panel, done → full layout.
3. Header: breadcrumb, statement, `<StatStrip>` from `MissionDetail.stat_strip`, meta line, ⋯ menu with Delete.
4. **Zone A — Outcome:** `<PositionsTable>`. Columns: ticker (links to `#memo-${ticker}`), weight, notional, entry price, current price, P&L pill. Sort by P&L descending by default.

**Day 2 of the phase (why + audit):**

5. **Zone B — Why:**
   - `<SubthemeCard>` grid (1 col mobile, 2 col tablet, 3 col desktop). Each card: name, description, candidate count, chosen ratio (dots: filled for chosen, hollow for passed), first 2 key findings.
   - `<ShortlistTable>`: ticker (links to memo), sub-theme, conviction, Chosen/Passed pill. Rows clickable.
6. **Zone C — Audit:**
   - `<ReportsToolbar>`: sort select (portfolio order | alpha | conviction | P&L), filter chips (all | fallback ⚠ | trap ⚖ | losing 📉), expand-all / collapse-all buttons.
   - `<MemoCard>` accordion. Summary row: ticker (anchor target), conviction badge, alignment badge, TA-rating badge, current P&L pill, `<WeakSpotIcons>`. Expanded: ported from `_memo_card.html` with the crit's fixes:
     - Fallback badge promoted to summary (already there via `<WeakSpotIcons>`); remove from card body.
     - Long descriptions: replace duplicate-preview pattern with a clean "show more" tail link via `<Accordion>`.
     - Markdown headings as `<h5>` blocks with margin (`<MdProse>` component using `react-markdown` with a custom `h1-h6` renderer).
   - `<TaDebate>`: reordered to debate-chronological (market → news → sentiment → fundamentals → investment_plan → trader_investment_plan → risk_debate_judge_decision → full_decision_markdown). PM full decision auto-open at top.

7. Add anchor scroll behavior: when navigating to `/missions/:id#memo-NRG`, scroll the NRG card into view and auto-expand it.

### Deliverables

- All three backfilled missions render top-to-bottom with the new layout.
- Click a position row → memo card opens.
- Click a Chosen row in shortlist → memo card opens.
- Weak-spot icons appear where expected (CCJ shows ⚠ if fallback, conviction-3 names show ⚖, losing positions show 📉).
- Two commits: `Build mission detail outcome zone` and `Build mission detail why + audit zones`.

### Tests for the gate

- ~10 Vitest cases on `<MemoCard>`, `<TaDebate>`, `<ReportsToolbar>` (sort and filter behavior), `<PositionsTable>` (sort + link behavior), `<SubthemeCard>` (chosen-ratio rendering).
- Dogfood: open each of the 3 backfilled missions, run the 5 explore-a-mission tasks (scan / drill / cross-ref / weak spots / decide), note friction in `docs/superpowers/notes/sprint-1-dogfood.md`.

---

## 7. Phase 6 · Cutover (~0.5 day)

**Goal.** Delete the Jinja UI, the templates, htmx, and the form-multipart dep.

### Build order

1. Delete `tacapes/dashboard/templates/` entirely.
2. Delete `tacapes/dashboard/static/htmx.min.js`.
3. Delete `tacapes/dashboard/routes.py` (the HTML-returning module).
4. Delete `tacapes/dashboard/filters.py` (logic ported to TS).
5. Remove `app.state.templates` wiring from `app.py`.
6. Update `app.py` to always mount the SPA at `/` and serve `index.html` for unmatched routes.
7. Remove `jinja2` and `python-multipart` from `pyproject.toml`. Re-run `pip install -e .[dev]` to confirm nothing else needs them.
8. Delete `tests/dashboard/test_routes.py`. Update any other test files that import the deleted modules.
9. Update `docs/superpowers/specs/2026-05-31-history-dashboard-design.md` with a top-of-file note: "§2 UI decision and §6 templates list superseded by `2026-05-31-dashboard-redesign-design.md` on 2026-XX-XX."
10. Update the `tacapes-v2 project` memory in `~/.claude/.../memory/` with what shipped.

### Deliverables

- One commit: `Delete Jinja UI in favor of SPA`.
- Repo no longer mentions Jinja except in archived spec.

### Tests for the gate

- `pytest tests/ -q` green (the diff is just deleting `test_routes.py`).
- `pnpm test` green.
- `ruff check tacapes/` clean.
- Dashboard runs in prod mode (`tacapes dashboard` → `:8732` serves the SPA).

---

## 8. Phase 7 · Test pass + dogfood + close (~1 day)

**Goal.** Last reflection, last polish, hand off to Sprint 2.

### Build order

1. Walk through the 5 explore-a-mission tasks against all 3 backfilled missions. Time each click sequence. Note ones that exceed expectation.
2. Quick-fix anything obvious (micro-spacing, weight tweaks, tooltip text).
3. Responsive check at 1280 / 1024 / 768 / 414 px. Position table overflow is acceptable at 414; document if so.
4. Write `docs/superpowers/notes/sprint-1-dogfood.md` with friction notes and what got fixed vs. what got punted to Sprint 2.
5. Append to `docs/superpowers/plans/2026-05-31-dashboard-redesign.md` a "Sprint 2 hopper" with the deferred items.
6. Update `~/.claude/.../memory/project_tacapes_v2.md` with the post-Sprint-1 state.
7. Commit message: `Sprint 1 close: dogfood notes, Sprint 2 hopper`.

### Ship gate

- `pytest tests/ -q` green
- `pnpm test` green
- `pnpm build` green, no TS errors
- `ruff check tacapes/` clean
- Dashboard renders all 3 backfilled missions in prod build with no console errors
- The 5 explore-a-mission tasks each take fewer clicks/scrolls than they did in the Jinja UI
- No new Python deps, two existing deps removed

---

## 9. Sprint 2 hopper (planned, not built)

Authored at sprint close (2026-05-31), expanded after the Phase 7 dogfood
pass. Sketch only — re-plan before executing.

### Originally deferred (carried over from spec §12)

- **Per-ticker drill page** `/missions/:id/tickers/:ticker` with the full narrative on one screen
- **Sticky ticker-nav chip row** for long missions
- **Header-level delete affordance**
- **Raw `notes/<TICKER>.md` link** per memo
- **Dark mode toggle**
- **Cost cap / pre-flight cost preview** on the new-mission form
- **Cancelling a running mission** from the UI
- **Playwright happy-path E2E**
- **`memo_writer` em-dash fallback string fix** (upstream code, separate slice)

### Added by the Phase 7 dogfood pass

See `docs/superpowers/notes/sprint-1-dogfood.md` for full context.

- **Multi-sub-theme attribution in the SubthemeCard grid.** Tickers that
  fit multiple sub-themes (e.g. GEV in mission `34bfb4f4` fits both
  `natural-gas-ai-bridge` and `grid-equipment-electrification`) currently
  appear under every sub-theme they fit. Either de-duplicate against the
  memo's primary `subtheme_id`, or render the non-primary attributions
  as ghost chips so the primary still reads as canonical.
- **Soften the "momentum trap" label.** LUMN in `7d27e8c6` flags as a
  trap (conviction 3 + diverged) but is +31.77%. The flag is useful as
  "scrutinise this," not "this is broken." Rename to "scrutinise," or
  drop the label entirely and rely on the ⚖ icon + tooltip.
- **Sticky first-column on `PositionsTable`.** At 414px the table scrolls
  horizontally and the ticker scrolls out of view, which makes the row
  hard to track. A sticky ticker column closes the gap. (Listed as
  "acceptable" in this plan's Phase 7 §3 — Sprint 2 polish.)
- **Spec amendment.** `2026-05-31-dashboard-redesign-design.md §4.2` says
  shortlist candidates carry `conviction` and `sub_theme_id` (singular).
  The wire shape is actually `sub_theme_ids[]` and no conviction; the
  fix is to compose lookups from the per-ticker memo. The implementation
  already does this; the spec line is now wrong. One-line edit on the
  next spec revision.
- **Tooltip text for `<WeakSpotIcons>`.** Current text is correct but
  reads dry. Worth a pass after a few real dogfood sessions to make the
  hover copy actionable ("This conviction flag often hits ahead of a
  re-rating" vs. the current "Conviction 3 + thesis diverged.").
- **Polling-test `act()` warning.** `src/api/missions.test.tsx` triggers
  a React `act()` warning when the fake-timer advance lands a state
  update outside `act`. Wrap the `advanceTimersByTimeAsync` calls in
  `act(async () => …)`. Pure cosmetic; the test is green.

---

## 10. Risk budget and contingencies

Total estimate: **7.5 working days**. Buffer: **2 days**.

| Risk | Likelihood | Mitigation |
|---|---|---|
| shadcn copy-paste components have TS errors against latest React | low | shadcn-cli is mature; fix per-component if it hits |
| `react-markdown` renders some of the analyst-report content poorly | medium | restrict plugin list, custom heading renderer, fall back to `<pre>` if a specific report breaks |
| Vite proxy doesn't pick up FastAPI's HTMX-style responses (no longer relevant — we deleted HTMX, but tests might be confused) | low | tests run against the JSON API only; proxy only matters at dev time |
| TanStack Query polling burns tokens / rate limits unnecessarily | low | `refetchInterval` only when status is non-terminal; stop polling on `done` / `failed` |
| Phase 5 (mission detail) overruns | high | scope ladder: if memo card filter/sort is too much, defer toolbar to Sprint 2; if `<TaDebate>` markdown rendering is fiddly, fall back to `<pre>` for one ship, fix in Sprint 2 |
| Old Jinja routes break during the parallel period (Phases 2-5) | low | tests catch it; don't touch `routes.py` until Phase 6 |
| `pnpm`/`npm` toolchain issues on the laptop | medium | document the exact `node --version` and `pnpm --version` in Phase 1's commit message |

**Cut-line for an over-budget Sprint 1:** drop the `<ReportsToolbar>` (sort/filter) and the `<SubthemeCard>` key-findings preview. Both are nice-to-have; the core P0/P1 wins land without them.

---

## 11. Decision log

Captured at plan-write time. Anything changed during execution should
append a row here.

| Decision | Choice | Why |
|---|---|---|
| Framework | Vite + React + TypeScript | No SSR needed; faster than Next.js for local SPA |
| Data layer | TanStack Query v5 | Built-in polling + cache replaces HTMX patterns cleanly |
| Component library | shadcn/ui | Copy-paste model, Radix accessibility, monochrome neutral palette fits a research tool |
| Forms | react-hook-form + zod | shadcn convention |
| Markdown | react-markdown + remark-gfm | Avoids a custom mdtext renderer; long analyst reports finally read as prose |
| Migration | Parallel API + UI for Phases 2-5, cutover in Phase 6 | Allows old UI to keep working as a reference |
| Per-ticker page | Deferred to Sprint 2 | Keeps Sprint 1 to one shippable slice |
| Dark mode | Tokens wired, toggle deferred | Adds work without solving a stated problem yet |
