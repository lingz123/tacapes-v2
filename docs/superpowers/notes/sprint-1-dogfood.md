# Sprint 1 dogfood notes

Date: 2026-05-31. Branch: `dashboard-redesign`. Author: implementer (me +
Claude pair) after Phase 6 cutover, before Sprint 1 close.

The five explore-a-mission tasks were walked against the three backfilled
missions: `34bfb4f4` and `ace4ec25` (both nuclear/energy mandates) and
`7d27e8c6` (photonics/networking). Findings live below.

---

## What worked

- **Outcome-first reordering is the win it was sold as.** Landing on
  `/missions/:id` puts the position table and the stat strip in the first
  viewport. For the two nuclear missions the user immediately sees "-3.5%"
  / "-6.1%" and which positions are dragging. The Jinja UI hid the same
  data behind two scrolls.
- **Cross-linking landed cleanly.** Position rows → `#memo-XYZ` →
  `MemoList` opens the matching accordion and scrolls it in. Confirmed
  end-to-end via `tacapes/dashboard/web/src/components/memo/MemoList.tsx:90`
  (the location.hash effect) against the three missions. Shortlist rows
  do the same via `window.location.hash`.
- **Weak-spot icons surface real signal.** On `34bfb4f4`, GEV carries all
  three flags (fallback + trap + losing) at once — the icon row makes
  that obvious from the collapsed audit zone. Mission `7d27e8c6` flags
  AVGO as fallback even though it's +4.28%, which is the kind of thing
  the user is meant to notice and override.
- **Sub-theme cards make the "Why" obvious.** Each mission has 4-5
  sub-themes; the dot-row + chosen ratio communicates "1 of 9 candidates
  chosen" at a glance. The fallback to "no description recorded" never
  fired against these three missions, but the contract is pinned in tests.

## What surprised me

- **Shortlist candidates do not carry `conviction` or `sub_theme_id`.**
  The actual wire shape (verified live against all 3 missions) is
  `{ ticker, company_name, mission_id, sub_theme_ids[], why_relevant }`.
  Conviction lives on the memo, not the candidate. Primary attribution
  comes from `memo.subtheme_id` (singular), with `candidate.sub_theme_ids[0]`
  as a fallback for shortlist-only names.
- **Some tickers belong to multiple sub-themes.** In mission `34bfb4f4`,
  GEV is in both `natural-gas-ai-bridge` and `grid-equipment-electrification`.
  Both sub-themes list it under `chosen_tickers`. The portfolio
  constructor settled on `natural-gas-ai-bridge` as the primary attribution
  (via `memo.subtheme_id`), but the UI doesn't surface "this ticker also
  fit theme B." Logged as a Sprint 2 hopper.
- **Fallback memos can dump huge prose into a single entity.** GEV in
  `34bfb4f4` has one "risk" whose `description` starts with
  `--- # COMPREHENSIVE TRADING & MACROECONOMIC REPORT` — the fallback
  writer pasted the TA report into `risks[0]` rather than parsing entities.
  The new `<MemoCard>`'s "show more" Accordion tail collapses this
  gracefully; the underlying upstream `memo_writer` bug stays a Sprint 2
  hopper.
- **Conviction-3 momentum-trap heuristic catches false positives.** LUMN
  in `7d27e8c6` is +31.77% but flags as a trap (conviction 3 +
  short_term_divergence). The flag is useful as a "scrutinise" signal,
  not a "this is broken" verdict. The label probably needs softening,
  not the formula.

## What got fixed in Phase 7

- **Shortlist table shape mismatch.**
  `tacapes/dashboard/web/src/components/detail/ShortlistTable.tsx`: now
  accepts `convictionByTicker` and `primarySubthemeByTicker` lookups
  composed from `memos_json` instead of reading non-existent
  `candidate.conviction` and `candidate.sub_theme_id` fields. Falls back
  to `sub_theme_ids[0]` for shortlist-only names with no memo. Pinned
  with 5 new vitest cases.
- **React Router v7 future-flag warnings.**
  `tacapes/dashboard/web/src/main.tsx`,
  `tacapes/dashboard/web/src/test/renderWithProviders.tsx`, and the
  inline router in `tacapes/dashboard/web/src/components/memo/ReportsToolbar.test.tsx`
  all set `future={{ v7_startTransition: true, v7_relativeSplatPath: true }}`.
  Behaviour change is a no-op for our routes; warning is gone.
- **Stale CLI docstring.** `tacapes/cli.py:436` said "FastAPI + HTMX".
  Now reads "FastAPI + React SPA on 127.0.0.1:8732".

## What got punted to Sprint 2

See `docs/superpowers/plans/2026-05-31-dashboard-redesign.md` §9 ("Sprint 2
hopper") for the full list. The dogfood pass added these on top of the
plan's original deferral list:

- **Multi-sub-theme attribution.** When a ticker fits multiple sub-themes,
  the sub-theme card grid currently lists it under every theme it fits.
  In a long mission that's mildly confusing. Either de-duplicate in
  favour of the memo's primary, or render secondary attributions as
  ghost chips.
- **Soften the "trap" label.** "Momentum trap" reads like a verdict.
  Rename to "scrutinise" or leave the icon (⚖) with a tooltip-only label.
- **`memo_writer` fallback dumps full TA report into `risks[0]`.** Already
  on the hopper as the "em-dash fallback string fix" — same upstream bug,
  same fix.
- **Polling `act()` warning** in `src/api/missions.test.tsx`. Cosmetic.
  Wrap the timer advances in `act(async () => …)` if it gets noisy.

## Click-count comparison

For each task, "new" = the SPA's path through the new IA, "old" = the
Jinja UI's path. Both counted from a fresh load on `/missions/:id`. A
"click" is anything that changes screen state (open accordion, nav,
toggle filter); a "scroll" is half a click.

| Task        | Old (Jinja) | New (SPA) |
|-------------|-------------|-----------|
| Scan        | 2 (scroll past 5 sections to position table) | 0 (visible above the fold) |
| Drill       | 3 (scroll up to reports, ctrl-F, expand) | 1 (click ticker in position row) |
| Cross-ref   | 4 (scroll to sub-themes, eyeball candidate list, scroll to shortlist, find row) | 2 (open memo, read `subtheme_id`; or sub-theme card → click chosen ticker) |
| Weak spots  | n/a (no signal in old UI) | 1 (filter chip) |
| Decide      | 5+ (scroll shortlist + scroll memos + ctrl-F + open memo + scan conviction) | 3 (sort=conviction, scan, click ticker) |

Old totals are estimates; new totals are reproduced against the three
backfilled missions. The "Weak spots" task didn't exist in the old UI as
anything other than "open every memo and read."

## Responsive check

Did not run a literal pixel test (no browser session here); did a code-level
audit of the breakpoints. Findings:

- **PositionsTable** has six fixed-width columns totalling ~640px before
  cell padding. shadcn's `<Table>` wraps in `relative w-full overflow-auto`
  so on a 414px viewport the table scrolls horizontally. Acceptable per
  spec §plan-§7-step-3. The sticky ticker column would be nice in Sprint 2.
- **SubthemeCard grid** steps 1 col (default) → 2 cols (`sm:`) → 3 cols
  (`lg:`). At 414px the cards stack; at 768px they pair; at 1024px+ they
  triple. Verified in `src/pages/MissionDetail.tsx` Zone B JSX.
- **ReportsToolbar** uses `flex-wrap`. Sort select (180px) + label + 4
  filter chips + expand/collapse split into two rows on mobile. Readable.
- **MemoCard summary row** is `flex flex-1 items-center gap-3 flex-wrap`.
  All badges wrap to a second row on narrow widths.
- **StatStrip** tiles are `flex-1 min-w-[140px]` inside a `flex-wrap`
  container — they collapse to two-up at ~580px and one-up below 320px.

No responsive bug worth fixing this sprint. Sprint 2 hopper for the
sticky ticker column on `PositionsTable`.

## Spec deltas worth flagging

- `2026-05-31-dashboard-redesign-design.md §4.2` says "candidates carry
  conviction + sub_theme_id." They don't. They carry `sub_theme_ids[]`
  and no conviction. The implementation handles this; the spec should be
  amended on the next revision. Logged as a one-line edit in the Sprint 2
  hopper.
- The same spec's §13 ("Sub-theme description for backfilled missions")
  flagged that backfilled `decomposition_json` may lack a `description`
  per sub-theme. In practice the three missions we have all carry a
  `hypothesis` field which the API maps to `description`
  (`tacapes/dashboard/api/routes.py:129`), so the fallback to "no
  description recorded" never actually fires against current data. Still
  pinned by tests.

---

Sprint 1 ships. Sprint 2 picks up from the hopper section of the redesign
plan + the items added above.
