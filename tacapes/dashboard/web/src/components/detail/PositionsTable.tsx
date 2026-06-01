/**
 * Outcome zone for the mission detail page.
 *
 * Renders one row per `PositionPnl`. Ticker cell links to `#memo-${ticker}`
 * so clicking jumps to the audit zone with the matching memo expanded
 * (anchor-scroll wired up by the detail page).
 *
 * Default sort is P&L descending so the best names sit at the top, the
 * unpriced (null pnl) rows sink to the bottom. Header clicks toggle the
 * sort key; sort direction inverts on a repeat click of the active column.
 */
import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PnlPill } from '@/components/stat/PnlPill';
import { usd } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PositionPnl } from '@/types/api';

type SortKey = 'ticker' | 'weight_pct' | 'notional_usd' | 'pnl_pct';
type SortDir = 'asc' | 'desc';

interface PositionsTableProps {
  positions: PositionPnl[];
  className?: string;
}

function comparator(a: PositionPnl, b: PositionPnl, key: SortKey, dir: SortDir): number {
  // Pull values, treating null as -Infinity so it sorts to the bottom on
  // desc (the default) and the top on asc.
  const sign = dir === 'asc' ? 1 : -1;
  if (key === 'ticker') {
    return sign * a.ticker.localeCompare(b.ticker);
  }
  const av = a[key];
  const bv = b[key];
  const an = av ?? -Infinity;
  const bn = bv ?? -Infinity;
  if (an === bn) return a.ticker.localeCompare(b.ticker);
  return sign * (an < bn ? -1 : 1);
}

function SortHeader({
  label,
  active,
  dir,
  align = 'left',
  onToggle,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  align?: 'left' | 'right';
  onToggle: () => void;
}) {
  const Icon = !active ? ArrowUpDown : dir === 'asc' ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground',
        align === 'right' && 'flex-row-reverse',
      )}
      data-active-sort={active ? dir : undefined}
    >
      <span>{label}</span>
      <Icon className={cn('size-3', !active && 'opacity-40')} aria-hidden="true" />
    </button>
  );
}

export function PositionsTable({ positions, className }: PositionsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('pnl_pct');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const sorted = useMemo(
    () => [...positions].sort((a, b) => comparator(a, b, sortKey, sortDir)),
    [positions, sortKey, sortDir],
  );

  const toggle = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Default direction: descending for numerics, ascending for ticker.
      setSortDir(key === 'ticker' ? 'asc' : 'desc');
    }
  };

  if (positions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">No positions recorded.</p>
    );
  }

  return (
    <div
      className={cn('rounded-lg border bg-card shadow-sm overflow-hidden', className)}
      data-testid="positions-table"
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-24">
              <SortHeader
                label="Ticker"
                active={sortKey === 'ticker'}
                dir={sortDir}
                onToggle={() => toggle('ticker')}
              />
            </TableHead>
            <TableHead className="w-24 text-right">
              <SortHeader
                label="Weight"
                active={sortKey === 'weight_pct'}
                dir={sortDir}
                align="right"
                onToggle={() => toggle('weight_pct')}
              />
            </TableHead>
            <TableHead className="w-28 text-right">
              <SortHeader
                label="Notional"
                active={sortKey === 'notional_usd'}
                dir={sortDir}
                align="right"
                onToggle={() => toggle('notional_usd')}
              />
            </TableHead>
            <TableHead className="w-28 text-right">Entry</TableHead>
            <TableHead className="w-28 text-right">Current</TableHead>
            <TableHead className="w-28 text-right">
              <SortHeader
                label="P&L"
                active={sortKey === 'pnl_pct'}
                dir={sortDir}
                align="right"
                onToggle={() => toggle('pnl_pct')}
              />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((p) => (
            <TableRow key={p.ticker} data-ticker={p.ticker}>
              <TableCell className="py-3 font-mono font-semibold">
                <a
                  href={`#memo-${p.ticker}`}
                  className="text-foreground hover:underline focus-visible:underline"
                  data-testid={`position-memo-link-${p.ticker}`}
                >
                  {p.ticker}
                </a>
              </TableCell>
              <TableCell className="py-3 text-right font-mono tabular-nums text-xs">
                {(p.weight_pct * 100).toFixed(1)}%
              </TableCell>
              <TableCell className="py-3 text-right font-mono tabular-nums text-xs">
                {usd(p.notional_usd)}
              </TableCell>
              <TableCell className="py-3 text-right font-mono tabular-nums text-xs">
                {usd(p.entry_price, { cents: true })}
                {p.entry_price_date && (
                  <span className="block text-[10px] text-muted-foreground">
                    {p.entry_price_date}
                  </span>
                )}
              </TableCell>
              <TableCell className="py-3 text-right font-mono tabular-nums text-xs">
                {usd(p.current_price, { cents: true })}
              </TableCell>
              <TableCell className="py-3 text-right whitespace-nowrap">
                <PnlPill value={p.pnl_pct} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
