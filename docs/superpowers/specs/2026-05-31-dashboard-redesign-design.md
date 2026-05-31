# tacapes: dashboard redesign (shadcn rewrite)

Design spec. Companion to `2026-05-31-history-dashboard-design.md` (the original
Jinja+HTMX slice) and **supersedes its §2 stack decision and §6 templates list**.
Source of truth for the dashboard-redesign slice.

Date: 2026-05-31. Authored after a design crit on the Jinja dashboard surfaced
five tasks the page makes hard (scan, drill, cross-reference, find weak spots,
decide), plus the visual-language fork.

Audience: implementer (you, with Claude pairing).

---

## 1. The problem

The Jinja+HTMX dashboard ships the data correctly but presents it as five
disconnected vertical sections (sub-theses, shortlist, reports, position
breakdown, delete). Outcomes from the design crit:

- **Scan is buried.** Position table + P&L are the last thing on the page;
  the user wants them first.
- **The narrative chain is broken.** README defines a per-ticker narrative
  (Why Shortlisted → TA Evaluation → Reconciled Memo). The page splits it
  across three non-linked sections.
- **No cross-linking.** Sub-theme → candidates → memo → position is the
  natural traversal. Today none of those rows are clickable.
- **Weak spots invisible.** Fallback memos, conviction-3 momentum traps, and
  losing positions are hidden in collapsed accordions.
- **Visually bare.** Hand-rolled CSS, no design tokens, flat hierarchy. Reads
  as a research-prototype admin page, not the audit tool you'd use to
  allocate real capital.

This slice rebuilds the dashboard as a **React + shadcn/ui SPA** against a
JSON API on FastAPI, with the information architecture from the crit.

---

## 2. Scope decisions (locked)

- **Stack: React + Vite + TypeScript + Tailwind + shadcn/ui.** Replaces
  Jinja + HTMX. Overrides §2 of the history-dashboard spec.
- **Routing: React Router v6.** Client-side. SPA hosted at the same origin
  as the FastAPI app, no SSR.
- **Data: TanStack Query v5.** Polling replaces HTMX `hx-trigger="every 3s"`
  via `refetchInterval` on the status query.
- **API: FastAPI serves `/api/*` JSON.** Existing HTML routes are kept for
  one phase as a fallback, then deleted along with `templates/` and
  `htmx.min.js`.
- **Information architecture: three vertical zones** — Outcome / Why /
  Audit — on the mission detail page. Per-ticker drill-down page is
  **deferred to Sprint 2**.
- **Visual reference: shadcn/ui defaults.** Neutral palette, Inter font,
  8px / 12px radii, hairline borders, subtle shadows. Dark mode wired in
  the token layer but disabled by default.
- **Authentication: none.** Dashboard binds to 127.0.0.1, matches the
  history-dashboard spec §12.
- **No live execution.** This is research / audit / portfolio review. No
  order routing, no API keys for brokers.
- **Tight scope.** Visual refresh + P0 + P1 from the crit. P2 per-ticker
  page, P3 polish (sticky nav, header-delete affordance, raw-notes link),
  and the `memo_writer` em-dash fallback-string fix all deferred.

---

## 3. Architecture

Two long-lived dev processes, one prod process.

```
┌─ DEV ─────────────────────────────────────────────────┐
│                                                       │
│   uvicorn :8732                vite :5173             │
│   FastAPI + Postgres           React + HMR            │
│         ▲                            │                │
│         └──── /api/* proxy ──────────┘                │
│                                                       │
│   You visit http://127.0.0.1:5173                     │
│                                                       │
└───────────────────────────────────────────────────────┘

┌─ PROD ────────────────────────────────────────────────┐
│                                                       │
│   `pnpm build` → tacapes/dashboard/web/dist/          │
│   FastAPI mounts dist/ as static + serves index.html  │
│   for any unmatched route (SPA fallback).             │
│   You visit http://127.0.0.1:8732                     │
│                                                       │
└───────────────────────────────────────────────────────┘
```

**Why Vite, not Next.js.** No SSR is needed (local single-user dashboard,
data is dynamic, SEO is irrelevant). Vite gives faster cold start, simpler
toolchain, no Node runtime in prod. Next.js would force a second runtime
process or static export — the latter is what Vite already does, without
the framework overhead.

**Why TanStack Query, not SWR or raw fetch.** Built-in polling, request
deduplication, cache invalidation. Replaces HTMX's per-element polling
with a per-query model that's easier to reason about.

**Why shadcn/ui specifically.** Copy-paste-into-repo model: components
live in `web/src/components/ui/` as TS source, edited like any other code,
no opaque dependency. Radix primitives underneath give accessibility for
free.

**Why no charts library.** Sprint 1 needs only tiny P&L sparklines.
Hand-rolled SVG is ~30 lines and avoids `recharts`-style 200KB additions.

---

## 4. API surface

FastAPI gains a parallel `/api/*` namespace. Pydantic response models
mirror existing repository functions. JSON shapes are derived from the
existing JSONB blobs verbatim where possible.

### 4.1 Endpoints

| Method · Path                              | Response                                                                                                                              | Notes                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `GET  /api/missions`                       | `{ missions: MissionListItem[], aggregate: AggregateStats }`                                                                            | Drives the index page                                  |
| `GET  /api/missions/:id`                   | `MissionDetail`  (full record incl. `decomposition_json`, `assessments_json`, `shortlist_json`, `ta_outputs_json`, `memos_json`, positions, current_prices) | Drives the detail page                                |
| `POST /api/missions`                       | `{ id: string }` + 201                                                                                                                  | Body matches `MissionConstraints` + statement + budget |
| `DELETE /api/missions/:id`                 | 204                                                                                                                                     | 409 if `status='running'`                              |
| `GET  /api/missions/:id/status`            | `{ status: 'queued'\|'running'\|'done'\|'failed', completed_at: string\|null }`                                                       | Polled at 3s while not terminal                        |
| `POST /api/prices/refresh`                 | 204                                                                                                                                     | Invalidates `price_quotes` cache                       |
| `GET  /healthz`                            | `{ ok: boolean }`                                                                                                                       | Unchanged                                              |

### 4.2 Response shapes

Defined as Pydantic models in `tacapes/dashboard/api/schemas.py`. The
existing JSONB structures (`memos_json`, `ta_outputs_json`,
`decomposition_json`, `assessments_json`, `shortlist_json`,
`portfolio_json`) are passed through as `dict[str, Any]` — the React app
treats them as documented in `tacapes/schemas/`.

New computed fields the API attaches:

- `MissionDetail.stat_strip` — `{ invested, current_value, pnl_pct, pnl_usd, unpriced_count, position_count, cash_reserve_pct }` so React doesn't recompute.
- `MissionDetail.subtheme_summary[]` — for each sub-theme: `{ id, name, description, candidate_count, chosen_count, chosen_tickers[] }` (the spec §5.3 join the Jinja version skipped).
- `MissionDetail.weak_spots` — per-ticker flags: `{ ticker, is_fallback_memo, is_momentum_trap, current_pnl_pct }` so the React UI can decorate summary rows without poking the raw memo.

### 4.3 What gets deleted

After Phase 6:

- `tacapes/dashboard/templates/` — all eight files
- `tacapes/dashboard/static/htmx.min.js`
- The HTML-returning routes in `tacapes/dashboard/routes.py`
- The Jinja env wiring in `tacapes/dashboard/app.py`
- The `jinja2` and `python-multipart` deps in `pyproject.toml` (multipart was only used for form posts; JSON API doesn't need it)

---

## 5. Information architecture

Mission detail page — three zones, top to bottom:

```
┌─ HEADER ──────────────────────────────────────────────┐
│ tacapes · breadcrumb                                  │
│ "Buy nuclear power names positioned to win..."        │
│                                                       │
│ ┌── stat strip ─────────────────────────────────┐    │
│ │ Invested  Current   P&L      Cash  Positions │    │
│ │ $20,000   $21,340   +6.7%↑   0%    4 of 4    │    │
│ └────────────────────────────────────────────────┘    │
│                                                       │
│ meta: 24mo · $42 spent · created 2026-05-12 · ⋯       │
├─ ZONE A · Outcome ────────────────────────────────────┤
│ Position breakdown                                    │
│ (table: ticker · weight · notional · entry · current  │
│  · P&L sparkline · P&L%, ticker cell links to memo)   │
├─ ZONE B · Why ────────────────────────────────────────┤
│ Sub-themes  (card grid: name · description ·         │
│              candidate dots · chosen ratio · key      │
│              findings preview)                        │
│ Shortlist   (table: ticker · sub-theme · conviction   │
│              · Chosen/Passed, all rows link to memo)  │
├─ ZONE C · Audit trail ────────────────────────────────┤
│ Reports                                               │
│ ┌── filter bar ────────────────────────────────┐     │
│ │ Sort: portfolio order · alpha · conviction · │     │
│ │   P&L                                         │     │
│ │ Filter: [ all ] [ fallback ⚠ ] [ trap ⚖ ]    │     │
│ │         [ losing 📉 ]                         │     │
│ │ [ expand all ] [ collapse all ]               │     │
│ └──────────────────────────────────────────────┘     │
│                                                       │
│ ──── 12 memo cards, accordion-collapsed ────          │
│ Each summary row:                                     │
│   TICKER · conviction badge · alignment badge ·       │
│   TA rating badge · current P&L · weak-spot icons     │
└───────────────────────────────────────────────────────┘
```

Mission list page — header strip + table:

```
┌─ HEADER ──────────────────────────────────────────────┐
│ tacapes                                               │
│ All-time: invested · current · P&L · spent            │
├───────────────────────────────────────────────────────┤
│ [ + New mission ]    [ Refresh prices ]               │
├───────────────────────────────────────────────────────┤
│ Status · Statement · Created · Cost · P&L · ⋯         │
│ (rows link to detail page)                            │
└───────────────────────────────────────────────────────┘
```

New mission form: shadcn `Dialog` triggered from `+ New mission`. Form
fields match the existing `POST /missions` payload. Validation via `zod`
schema mirroring the FastAPI Pydantic constraints.

---

## 6. Design tokens

Token names align with Tailwind + shadcn defaults so the ecosystem
plugs in. Stored in `web/src/styles/tokens.css` as CSS variables, mirrored
in `tailwind.config.ts`.

### Color (light theme, defaults; dark mode tokens wired but not surfaced)

```
--background        oklch(0.99 0 0)         /* page */
--foreground        oklch(0.20 0 0)
--card              oklch(1    0 0)         /* surface */
--card-foreground   oklch(0.20 0 0)
--muted             oklch(0.96 0 0)
--muted-foreground  oklch(0.50 0 0)
--border            oklch(0.92 0 0)
--input             oklch(0.92 0 0)
--ring              oklch(0.70 0 0)

--primary           oklch(0.20 0 0)         /* neutral dark, monochrome */
--primary-foreground oklch(0.98 0 0)

--good              oklch(0.62 0.18 145)    /* emerald-ish */
--good-bg           oklch(0.97 0.03 145)
--warn              oklch(0.72 0.16 75)     /* amber-ish */
--warn-bg           oklch(0.97 0.04 80)
--bad               oklch(0.60 0.20 25)     /* rose-ish */
--bad-bg            oklch(0.97 0.04 25)
--info              oklch(0.60 0.18 245)    /* blue-ish */
--info-bg           oklch(0.97 0.03 245)
```

P&L up/down map to `--good` / `--bad`.

### Typography

- Body: **Inter** via `@fontsource-variable/inter`.
- Mono: **JetBrains Mono** via `@fontsource-variable/jetbrains-mono`, used for tickers and prices.
- Scale (px): 11 / 12 / 13 / 14 (body) / 16 / 18 / 22 / 28 / 36.
- Weight: 400 / 500 / 600 / 700.
- Line-height: 1.4 (body) / 1.2 (headings) / 1.55 (long prose).

### Spacing, radius, shadow

- Spacing scale (Tailwind defaults): `1=4px, 2=8px, 3=12px, 4=16px, 5=20px, 6=24px, 8=32px, 12=48px`.
- Radius: `--radius-sm 4px`, `--radius 8px` (default), `--radius-lg 12px` (cards), `--radius-xl 16px` (hero).
- Shadow: `--shadow-sm 0 1px 2px rgba(0,0,0,.04)`, `--shadow 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04)`.

---

## 7. Component inventory

### From shadcn/ui (copy-paste into `web/src/components/ui/`)

`Button`, `Badge`, `Card`, `Table`, `Tabs`, `Accordion`, `Separator`,
`Tooltip`, `Dialog`, `Skeleton`, `Sonner` (toasts), `ScrollArea`,
`Input`, `Label`, `Select`, `Textarea`, `Form` (react-hook-form wrappers).

### Custom domain components (under `web/src/components/`)

| Component                | Where used                | Notes                                                       |
| ------------------------ | ------------------------- | ----------------------------------------------------------- |
| `<TopBar>`               | app shell                 | brand + nav + global actions                                |
| `<StatStrip>`            | detail header, list header | 4-6 stat tiles in a row, responsive                          |
| `<ConvictionBadge>`      | summary rows, memo cards  | wraps `<Badge>`, computes good/warn/bad from 1-5 number      |
| `<AlignmentBadge>`       | summary rows, memo cards  | wraps `<Badge>`, computes color from `ThesisAlignment`       |
| `<RatingBadge>`          | summary rows, memo cards  | wraps `<Badge>`, computes color from `PortfolioRating`       |
| `<PnlPill>`              | positions, memo summary   | "+6.7%" colored, with optional inline sparkline              |
| `<Sparkline>`            | inside `<PnlPill>` and positions table | hand-rolled SVG, ~12px tall, 30 data points (or fewer) |
| `<WeakSpotIcons>`        | report summary rows       | renders ⚠ / ⚖ / 📉 with Tooltips explaining each              |
| `<MemoCard>`             | reports section           | port of `_memo_card.html`                                    |
| `<TaDebate>`             | reports section           | port of `_ta_debate.html`, debate-chronological order        |
| `<MdProse>`              | inside `<TaDebate>` and entity descriptions | `react-markdown` with `remark-gfm`, restricted plugins, custom `h1-h6` → block heading components |
| `<SubthemeCard>`         | sub-themes section        | card with candidate dots and chosen ratio                    |
| `<ShortlistTable>`       | shortlist section         | shadcn `<Table>`, sub-theme column, links to memo anchor     |
| `<PositionsTable>`       | outcome zone              | shadcn `<Table>`, sparkline column, P&L column, links to memo anchor |
| `<ReportsToolbar>`       | audit zone                | sort + filter + expand/collapse-all                          |
| `<MissionRow>`           | list page                 | shadcn `<TableRow>`, P&L pill, status badge, ⋯ menu          |
| `<NewMissionDialog>`     | list page                 | `<Dialog>` + `<Form>` for `POST /api/missions`               |

### What deliberately is NOT custom

The five HTML routes the Jinja templates served (index, mission_new,
mission_detail, status, _failed). React Router renders them; FastAPI no
longer knows the page exists.

---

## 8. Migration strategy

Backend and frontend land in alternating phases so the dashboard is never
broken on `main`:

1. **Phase 2 lands the JSON API alongside the HTML routes.** Existing tests
   keep passing; HTML routes keep serving the current Jinja UI.
2. **Phases 3-5 build the React app against the JSON API.** Dev workflow
   is `vite dev` for the new UI; the Jinja UI is still reachable at
   `/missions/<id>` if you need to compare.
3. **Phase 6 deletes the Jinja UI, the templates, htmx, and the
   form-multipart dep.** FastAPI mounts the Vite build, with an SPA
   fallback handler that returns `index.html` for any unmatched route.

`history-dashboard` branch stays as-is. A fresh branch
`dashboard-redesign` is cut from current HEAD for this work.

---

## 9. Testing

### Backend (Python)

- New `tests/dashboard/test_api.py` — JSON contract tests via FastAPI
  `TestClient`, covering each `/api/*` endpoint shape and the polling
  endpoint's cache behaviour.
- Existing `tests/dashboard/test_routes.py` — keep until Phase 6, then
  delete (the assertions about HTML body content are now meaningless).
- The 16 dashboard tests we have today + ~8-12 new JSON-shape tests =
  expect ~24-28 backend tests after the dust settles.

### Frontend (TypeScript)

- **Vitest + @testing-library/react** for component tests. Targets:
  derived classes on `<ConvictionBadge>` / `<AlignmentBadge>` /
  `<RatingBadge>` / `<PnlPill>`, `<StatStrip>` aggregate math,
  `<ReportsToolbar>` sort/filter behavior, `<NewMissionDialog>` form
  validation.
- **MSW** (Mock Service Worker) to stub `/api/*` in tests so component
  tests don't touch the live backend.
- **No Playwright in Sprint 1.** One happy-path E2E (load list → open
  detail → see expected counts) is a Sprint 2 P3 if dogfooding surfaces
  recurring breakage.

### Ship gate

- `pytest tests/dashboard/ -q` green
- `pnpm test` green
- `pnpm build` succeeds with no TS errors
- `ruff check tacapes/` clean
- All three backfilled missions render top-to-bottom in the new UI
  without console errors

---

## 10. New dependencies

### Backend (Python, `pyproject.toml`)

Add nothing. Remove (in Phase 6): `jinja2`, `python-multipart`.

### Frontend (`tacapes/dashboard/web/package.json`)

```
"dependencies": {
  "react": "^18.3",
  "react-dom": "^18.3",
  "react-router-dom": "^6.26",
  "@tanstack/react-query": "^5.50",
  "react-hook-form": "^7.52",
  "zod": "^3.23",
  "@hookform/resolvers": "^3.9",
  "react-markdown": "^9.0",
  "remark-gfm": "^4.0",
  "lucide-react": "^0.428",
  "class-variance-authority": "^0.7",
  "clsx": "^2.1",
  "tailwind-merge": "^2.5",
  "@fontsource-variable/inter": "^5.1",
  "@fontsource-variable/jetbrains-mono": "^5.1",
  "sonner": "^1.5"
}
"devDependencies": {
  "vite": "^5.4",
  "@vitejs/plugin-react": "^4.3",
  "typescript": "^5.5",
  "tailwindcss": "^3.4",
  "postcss": "^8.4",
  "autoprefixer": "^10.4",
  "vitest": "^2.0",
  "@testing-library/react": "^16.0",
  "@testing-library/jest-dom": "^6.4",
  "@testing-library/user-event": "^14.5",
  "msw": "^2.4",
  "jsdom": "^25.0",
  "@types/react": "^18.3",
  "@types/react-dom": "^18.3"
}
```

shadcn/ui components are not a dependency — they're copied into
`web/src/components/ui/` via `pnpm dlx shadcn@latest add <component>`.

Tooling: pnpm preferred (faster install, stricter resolution), npm
acceptable. The CI command stays `pnpm install && pnpm build && pnpm
test`.

---

## 11. New layout

```
tacapes/
├── dashboard/
│   ├── app.py                        # FastAPI app, mounts api/ + dist/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                 # the /api/* handlers
│   │   └── schemas.py                # Pydantic response models
│   ├── jobs.py                       # unchanged
│   ├── runners.py                    # unchanged
│   ├── prices.py                     # unchanged
│   ├── backfill.py                   # unchanged
│   ├── db/                           # unchanged
│   └── web/                          # NEW: the React app
│       ├── index.html
│       ├── vite.config.ts            # /api proxy → :8732
│       ├── tailwind.config.ts
│       ├── postcss.config.js
│       ├── tsconfig.json
│       ├── package.json
│       ├── public/
│       └── src/
│           ├── main.tsx
│           ├── App.tsx               # router
│           ├── api/                  # TanStack Query hooks + fetchers
│           ├── components/
│           │   ├── ui/               # shadcn copy-pasted primitives
│           │   ├── memo/             # MemoCard, TaDebate, MdProse, etc.
│           │   ├── stat/             # StatStrip, PnlPill, Sparkline
│           │   └── shell/            # TopBar, layout
│           ├── pages/
│           │   ├── MissionList.tsx
│           │   └── MissionDetail.tsx
│           ├── styles/
│           │   ├── globals.css       # Tailwind directives + tokens
│           │   └── tokens.css        # the design-token CSS vars
│           ├── types/                # mirrors tacapes/schemas/ shapes
│           └── lib/
│               ├── format.ts         # currency, percent, date
│               └── derive.ts         # weak-spot flags, conviction colors
```

After Phase 6 deletion:

- `tacapes/dashboard/templates/` — gone
- `tacapes/dashboard/static/htmx.min.js` — gone
- `tacapes/dashboard/routes.py` — replaced by `api/routes.py`
- `tacapes/dashboard/filters.py` — gone (filters become TS helpers in `web/src/lib/derive.ts`)

---

## 12. Explicitly deferred to Sprint 2

- **Per-ticker drill page** at `/missions/:id/tickers/:ticker` with the full
  narrative (sub-theme card + shortlist rationale + TA debate + memo) on one screen.
- **Sticky ticker-nav chip row** for long missions.
- **Header-level delete affordance** (currently bottom-of-page in Jinja; the
  redesign keeps it in the ⋯ menu only).
- **Raw `notes/<TICKER>.md` link** from each memo card.
- **`memo_writer` em-dash fallback string fix** (upstream code, not a UI change).
- **Dark mode toggle.** Tokens are dark-mode-ready, toggle is a Sprint 2 ship.
- **Cost cap / pre-flight cost preview** on the new-mission form.
- **Cancelling a running mission** from the UI.
- **Playwright E2E coverage.**

---

## 13. Open questions

- **Sub-theme description for backfilled missions.** Backfilled
  `decomposition_json` may lack `description` per sub-theme; assessment
  `key_findings` may also be empty for missions that ran before that field
  existed. The `<SubthemeCard>` needs to render an "no description recorded"
  fallback gracefully. Need a sample check at Phase 5.
- **Sparkline data source.** We only persist `entry_price` and current
  `price_quotes.price`. A real sparkline needs intra-period prices we don't
  have. Sprint 1 ships an "arrow + percent" pill, not a true sparkline;
  rename `<Sparkline>` to `<PnlArrow>` if the real version doesn't
  materialise.
- **Dev port collision.** Vite defaults to :5173; that's usually free, but
  confirm before Phase 1.
