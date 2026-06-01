/**
 * Toolbar for the Audit zone's memo accordion.
 *
 * Sort + filter both live in URL search params so deep links survive a page
 * reload. The supported params are:
 *   ?sort=portfolio|alpha|conviction|pnl   (default: portfolio)
 *   ?filter=all|fallback|trap|losing       (default: all)
 *
 * Filter chips are mutually exclusive — picking "fallback" replaces the
 * previous filter rather than stacking. The expand-all / collapse-all
 * buttons fire callbacks the consumer wires to its Accordion `value` state.
 */
import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronsDown, ChevronsUp, AlertTriangle, Scale, TrendingDown } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

export type MemoSort = 'portfolio' | 'alpha' | 'conviction' | 'pnl';
export type MemoFilter = 'all' | 'fallback' | 'trap' | 'losing';

const SORTS: { value: MemoSort; label: string }[] = [
  { value: 'portfolio', label: 'Portfolio order' },
  { value: 'alpha', label: 'Alphabetical' },
  { value: 'conviction', label: 'Conviction' },
  { value: 'pnl', label: 'P&L' },
];

const FILTERS: { value: MemoFilter; label: string; Icon?: typeof AlertTriangle }[] = [
  { value: 'all', label: 'All' },
  { value: 'fallback', label: 'Fallback', Icon: AlertTriangle },
  { value: 'trap', label: 'Trap', Icon: Scale },
  { value: 'losing', label: 'Losing', Icon: TrendingDown },
];

interface ReportsToolbarProps {
  onExpandAll: () => void;
  onCollapseAll: () => void;
  className?: string;
}

export function ReportsToolbar({
  onExpandAll,
  onCollapseAll,
  className,
}: ReportsToolbarProps) {
  const [params, setParams] = useSearchParams();
  const sort = (params.get('sort') as MemoSort) || 'portfolio';
  const filter = (params.get('filter') as MemoFilter) || 'all';

  const updateParams = useCallback(
    (next: Partial<{ sort: MemoSort; filter: MemoFilter }>) => {
      const newParams = new URLSearchParams(params);
      // Default values stay implicit — keeps the URL clean.
      if (next.sort != null) {
        if (next.sort === 'portfolio') newParams.delete('sort');
        else newParams.set('sort', next.sort);
      }
      if (next.filter != null) {
        if (next.filter === 'all') newParams.delete('filter');
        else newParams.set('filter', next.filter);
      }
      setParams(newParams, { replace: true });
    },
    [params, setParams],
  );

  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-3 rounded-md border bg-card px-3 py-2 shadow-sm',
        className,
      )}
      data-testid="reports-toolbar"
      data-sort={sort}
      data-filter={filter}
    >
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-muted-foreground" htmlFor="sort-select">
          Sort
        </label>
        <Select
          value={sort}
          onValueChange={(value) => updateParams({ sort: value as MemoSort })}
        >
          <SelectTrigger
            id="sort-select"
            className="h-8 w-[180px]"
            data-testid="sort-select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORTS.map((s) => (
              <SelectItem key={s.value} value={s.value} data-value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="ml-2 flex flex-wrap gap-1" role="group" aria-label="Filter memos">
          {FILTERS.map(({ value, label, Icon }) => {
            const active = filter === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => updateParams({ filter: value })}
                aria-pressed={active}
                data-testid={`filter-${value}`}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition',
                  active
                    ? 'border-foreground bg-foreground text-background'
                    : 'border-border bg-background text-muted-foreground hover:text-foreground',
                )}
              >
                {Icon && <Icon className="size-3" />}
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Button
          size="sm"
          variant="ghost"
          onClick={onExpandAll}
          data-testid="expand-all"
          className="text-xs"
        >
          <ChevronsDown className="mr-1 size-3" />
          Expand all
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onCollapseAll}
          data-testid="collapse-all"
          className="text-xs"
        >
          <ChevronsUp className="mr-1 size-3" />
          Collapse all
        </Button>
      </div>
    </div>
  );
}
