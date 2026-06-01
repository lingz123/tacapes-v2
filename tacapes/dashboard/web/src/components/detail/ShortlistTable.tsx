/**
 * Shortlist table for Zone B (Why).
 *
 * Reads `shortlist_json.candidates` directly. The actual shape (verified on
 * 2026-05-31 against the 3 backfilled missions) is:
 *   - ticker, company_name, mission_id
 *   - sub_theme_ids: string[]   (a candidate can belong to multiple themes)
 *   - why_relevant: string
 *
 * Conviction is NOT on the candidate row; it lives on the per-ticker memo.
 * We accept a `convictionByTicker` lookup so the consumer can compose the
 * right value once and pass it in.
 *
 * Primary sub-theme attribution uses `memo.subtheme_id` (singular) when
 * available — that's the sub-theme the portfolio constructor settled on
 * for the ticker — and falls back to `candidate.sub_theme_ids[0]` for
 * shortlist-only names. Names that appear in multiple sub-themes still
 * show only their primary attribution to keep the column scannable.
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
  /** Plural in the wire shape; a candidate can fit multiple sub-themes. */
  sub_theme_ids?: string[] | null;
  /** Legacy singular form. Older snapshots may emit this; treat as fallback. */
  sub_theme_id?: string | null;
  /** Pre-pipeline rationale ("why we shortlisted"). Not currently rendered;
   *  reserved for a tooltip / drill page. */
  why_relevant?: string | null;
  company_name?: string | null;
}

interface ShortlistTableProps {
  /** Raw candidates from `shortlist_json.candidates`. */
  candidates: ShortlistCandidate[];
  /** Tickers that survived to the portfolio. Mirrors `MissionDetail.chosen_tickers`. */
  chosen: string[];
  /** Map from sub-theme id to display name. Falls back to the id when absent. */
  subthemeNames?: Record<string, string>;
  /** Ticker → memo conviction. Composed by the consumer so the table
   *  doesn't have to reach into `memos_json` itself. */
  convictionByTicker?: Record<string, number | null>;
  /** Ticker → memo's primary sub-theme attribution. Falls back to
   *  `candidate.sub_theme_ids[0]` per row when absent. */
  primarySubthemeByTicker?: Record<string, string | null>;
}

function primarySubtheme(
  c: ShortlistCandidate,
  primaryByTicker: ShortlistTableProps['primarySubthemeByTicker'],
): string | null {
  const primary = primaryByTicker?.[c.ticker];
  if (primary) return primary;
  if (c.sub_theme_id) return c.sub_theme_id;
  const ids = c.sub_theme_ids ?? [];
  return ids[0] ?? null;
}

export function ShortlistTable({
  candidates,
  chosen,
  subthemeNames,
  convictionByTicker,
  primarySubthemeByTicker,
}: ShortlistTableProps) {
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
            const subId = primarySubtheme(c, primarySubthemeByTicker) ?? '';
            const subLabel = subthemeNames?.[subId] ?? subId;
            const conv = convictionByTicker?.[c.ticker] ?? null;
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
                  <ConvictionBadge value={conv} />
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
