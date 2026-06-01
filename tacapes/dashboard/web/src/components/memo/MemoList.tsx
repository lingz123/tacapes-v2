/**
 * Zone C container. Owns the open-accordion state and listens for hash
 * changes so navigating to `/missions/:id#memo-NRG` (from a position row,
 * a shortlist row, or an external link) scrolls the matching card into
 * view and auto-expands it.
 *
 * Sort and filter are read from URL search params via <ReportsToolbar> so
 * deep links survive a reload. Polling and other data concerns stay in the
 * page; this component is pure presentation + local UI state.
 */
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';

import { Accordion } from '@/components/ui/accordion';
import { ReportsToolbar, type MemoFilter, type MemoSort } from './ReportsToolbar';
import { MemoCard, type Memo } from './MemoCard';
import type { TaOutputs } from './TaDebate';
import type { WeakSpot } from '@/types/api';

interface MemoListProps {
  /** Raw `memos_json` dict from MissionDetail. */
  memos: Record<string, Memo>;
  /** Raw `ta_outputs_json` dict from MissionDetail. */
  taOutputs: Record<string, TaOutputs> | null | undefined;
  /** `weak_spots[]`, indexable by ticker. */
  weakSpots: WeakSpot[];
  /** Ticker ordering as it landed in the portfolio. The "Portfolio order" sort
   *  honours this; everything else uses its own key. */
  portfolioOrder: string[];
}

function comparator(
  a: string,
  b: string,
  sort: MemoSort,
  byTicker: {
    conviction: Record<string, number | null>;
    pnl: Record<string, number | null>;
    portfolio: Record<string, number>;
  },
): number {
  switch (sort) {
    case 'alpha':
      return a.localeCompare(b);
    case 'conviction': {
      const av = byTicker.conviction[a] ?? -Infinity;
      const bv = byTicker.conviction[b] ?? -Infinity;
      if (av === bv) return a.localeCompare(b);
      return bv - av;
    }
    case 'pnl': {
      const av = byTicker.pnl[a] ?? -Infinity;
      const bv = byTicker.pnl[b] ?? -Infinity;
      if (av === bv) return a.localeCompare(b);
      return bv - av;
    }
    case 'portfolio':
    default: {
      // Portfolio rows first (in their original order), then everything else
      // alphabetical. Missing → +Infinity sinks to the bottom.
      const av = byTicker.portfolio[a] ?? Infinity;
      const bv = byTicker.portfolio[b] ?? Infinity;
      if (av === bv) return a.localeCompare(b);
      return av - bv;
    }
  }
}

function matchesFilter(filter: MemoFilter, spot: WeakSpot | undefined): boolean {
  if (!spot) return filter === 'all';
  switch (filter) {
    case 'all':
      return true;
    case 'fallback':
      return spot.is_fallback_memo;
    case 'trap':
      return spot.is_momentum_trap;
    case 'losing':
      return spot.is_losing;
  }
}

export function MemoList({ memos, taOutputs, weakSpots, portfolioOrder }: MemoListProps) {
  const [openItems, setOpenItems] = useState<string[]>([]);
  const [params] = useSearchParams();
  const location = useLocation();

  const sort = (params.get('sort') as MemoSort) || 'portfolio';
  const filter = (params.get('filter') as MemoFilter) || 'all';

  const tickers = Object.keys(memos);
  const weakByTicker = useMemo(() => {
    const out: Record<string, WeakSpot> = {};
    for (const w of weakSpots) out[w.ticker] = w;
    return out;
  }, [weakSpots]);

  const byTicker = useMemo(() => {
    const conviction: Record<string, number | null> = {};
    const pnl: Record<string, number | null> = {};
    const portfolio: Record<string, number> = {};
    for (const t of tickers) {
      conviction[t] = typeof memos[t]?.conviction === 'number' ? (memos[t]!.conviction as number) : null;
      pnl[t] = weakByTicker[t]?.current_pnl_pct ?? null;
    }
    portfolioOrder.forEach((t, i) => (portfolio[t] = i));
    return { conviction, pnl, portfolio };
  }, [tickers, memos, weakByTicker, portfolioOrder]);

  const visible = useMemo(() => {
    return tickers
      .filter((t) => matchesFilter(filter, weakByTicker[t]))
      .sort((a, b) => comparator(a, b, sort, byTicker));
  }, [tickers, filter, sort, weakByTicker, byTicker]);

  // Anchor scroll: when the URL hash points at #memo-XYZ, ensure XYZ is in
  // the open set and scroll its element into view. Wait one tick so the
  // Accordion has rendered the new content before scrolling.
  useEffect(() => {
    const hash = location.hash;
    if (!hash.startsWith('#memo-')) return;
    const ticker = hash.slice('#memo-'.length);
    if (!ticker || !memos[ticker]) return;
    setOpenItems((prev) => (prev.includes(ticker) ? prev : [...prev, ticker]));
    const t = window.setTimeout(() => {
      const el = document.getElementById(`memo-${ticker}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
    return () => window.clearTimeout(t);
  }, [location.hash, memos]);

  const handleExpandAll = () => setOpenItems([...visible]);
  const handleCollapseAll = () => setOpenItems([]);

  if (tickers.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">No reports recorded.</p>
    );
  }

  return (
    <div className="space-y-3">
      <ReportsToolbar onExpandAll={handleExpandAll} onCollapseAll={handleCollapseAll} />

      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground italic" data-testid="filter-empty">
          No memos match the current filter.
        </p>
      ) : (
        <Accordion
          type="multiple"
          value={openItems}
          onValueChange={setOpenItems}
          className="rounded-lg border bg-card shadow-sm overflow-hidden"
          data-testid="memo-list"
        >
          {visible.map((ticker) => (
            <MemoCard
              key={ticker}
              ticker={ticker}
              memo={memos[ticker] ?? {}}
              ta={taOutputs?.[ticker]}
              weakSpot={weakByTicker[ticker]}
              rating={taOutputs?.[ticker]?.rating ?? null}
            />
          ))}
        </Accordion>
      )}
    </div>
  );
}
