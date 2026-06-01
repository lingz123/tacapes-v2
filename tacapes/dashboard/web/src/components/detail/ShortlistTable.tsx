/**
 * Shortlist table for Zone B (Why).
 *
 * Reads `shortlist_json.candidates` directly. The schema is the assessments
 * pipeline's per-ticker candidate row, which guarantees `ticker` and usually
 * carries `conviction` + `sub_theme_id` + `rationale`. Anything missing
 * renders as a dash so backfilled missions don't crash.
 *
 * Rows are clickable and link the ticker cell to the matching memo anchor;
 * clicking anywhere on the row also navigates (handled with a hash change).
 */
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ConvictionBadge } from '@/components/stat/ConvictionBadge';
import { cn } from '@/lib/utils';
import { semanticClasses } from '@/lib/derive';

interface ShortlistCandidate {
  ticker: string;
  sub_theme_id?: string | null;
  conviction?: number | string | null;
  rationale?: string | null;
}

interface ShortlistTableProps {
  /** Raw candidates from `shortlist_json.candidates`. */
  candidates: ShortlistCandidate[];
  /** Tickers that survived to the portfolio. Mirrors `MissionDetail.chosen_tickers`. */
  chosen: string[];
  /** Map from sub-theme id to display name. Falls back to the id when absent. */
  subthemeNames?: Record<string, string>;
}

export function ShortlistTable({ candidates, chosen, subthemeNames }: ShortlistTableProps) {
  if (candidates.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">No shortlist recorded.</p>
    );
  }

  const chosenSet = new Set(chosen);
  const chosenClasses = semanticClasses('good');
  const passedClasses = semanticClasses('neutral');

  const onRowClick = (ticker: string) => {
    // Update the URL hash so the audit zone's anchor-scroll logic picks it
    // up and expands the matching memo. History-stack push is fine — back
    // returns to the previous hash.
    window.location.hash = `memo-${ticker}`;
  };

  return (
    <div
      className="rounded-lg border bg-card shadow-sm overflow-hidden"
      data-testid="shortlist-table"
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-24">Ticker</TableHead>
            <TableHead>Sub-theme</TableHead>
            <TableHead className="w-28">Conviction</TableHead>
            <TableHead className="w-24 text-right">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {candidates.map((c) => {
            const isChosen = chosenSet.has(c.ticker);
            const subId = c.sub_theme_id ?? '';
            const subLabel = subthemeNames?.[subId] ?? subId ?? '—';
            return (
              <TableRow
                key={c.ticker}
                className="cursor-pointer hover:bg-muted/40"
                onClick={() => onRowClick(c.ticker)}
                data-ticker={c.ticker}
                data-chosen={isChosen ? 'yes' : 'no'}
              >
                <TableCell className="py-3 font-mono font-semibold">
                  <a
                    href={`#memo-${c.ticker}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-foreground hover:underline focus-visible:underline"
                    data-testid={`shortlist-memo-link-${c.ticker}`}
                  >
                    {c.ticker}
                  </a>
                </TableCell>
                <TableCell className="py-3 text-xs text-muted-foreground">
                  {subLabel || <span className="italic">—</span>}
                </TableCell>
                <TableCell className="py-3">
                  <ConvictionBadge value={c.conviction ?? null} />
                </TableCell>
                <TableCell className="py-3 text-right">
                  <Badge
                    variant="outline"
                    data-variant={isChosen ? 'good' : 'neutral'}
                    className={cn(
                      'font-medium',
                      isChosen ? cn(chosenClasses.bg, chosenClasses.text, chosenClasses.border)
                               : cn(passedClasses.bg, passedClasses.text, passedClasses.border),
                    )}
                  >
                    {isChosen ? 'Chosen' : 'Passed'}
                  </Badge>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

export type { ShortlistCandidate };
