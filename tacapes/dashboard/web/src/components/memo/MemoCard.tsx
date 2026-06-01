/**
 * Per-ticker memo card. Port of `_memo_card.html` with the design-crit fixes:
 *
 *   - Fallback warning is no longer duplicated in the card body; it lives in
 *     the summary row via <WeakSpotIcons>.
 *   - Long entity descriptions use a shadcn Accordion "show more" tail
 *     instead of the Jinja duplicate-preview + <details> pair.
 *   - Markdown headings render as block <h5>-style headings via <MdProse>,
 *     so a section labelled "Drivers" sits visually distinct from prose.
 *
 * The component itself is one shadcn AccordionItem. The parent <MemoList>
 * controls which cards are expanded so toolbar actions (expand-all,
 * filter-driven anchor jumps) reach into the same state.
 */
import { ChevronDown } from 'lucide-react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ConvictionBadge } from '@/components/stat/ConvictionBadge';
import { AlignmentBadge } from '@/components/stat/AlignmentBadge';
import { RatingBadge } from '@/components/stat/RatingBadge';
import { PnlPill } from '@/components/stat/PnlPill';
import { WeakSpotIcons } from './WeakSpotIcons';
import { MdProse } from './MdProse';
import { TaDebate, type TaOutputs } from './TaDebate';
import { cn } from '@/lib/utils';
import type { WeakSpot } from '@/types/api';

interface Entity {
  name?: string | null;
  description?: string | null;
  importance?: string | null;
  severity?: string | null;
  likelihood?: string | null;
  impact?: string | null;
  expected_window?: string | null;
}

interface Valuation {
  price_target?: number | null;
  methodology?: string | null;
}

interface KeyNumber {
  label?: string | null;
  value?: string | number | null;
  unit?: string | null;
  period?: string | null;
}

interface Memo {
  ticker?: string;
  thesis_one_liner?: string | null;
  conviction?: number | null;
  thesis_alignment?: string | null;
  subtheme_id?: string | null;
  last_refreshed?: string | null;
  reconciliation_notes?: string | null;
  drivers?: Entity[] | null;
  risks?: Entity[] | null;
  catalysts?: Entity[] | null;
  valuation?: Partial<Record<'bear' | 'base' | 'bull' | 'current', Valuation>> | null;
  key_numbers?: KeyNumber[] | null;
  thesis_breakers?: string[] | null;
}

interface MemoCardProps {
  ticker: string;
  memo: Memo;
  ta?: TaOutputs | null;
  weakSpot?: WeakSpot | null;
  /** TA rating, optional shortcut so the summary row can show it without
   *  the consumer reaching into ta_outputs_json itself. */
  rating?: string | null;
  className?: string;
}

export function MemoCard({
  ticker,
  memo,
  ta,
  weakSpot,
  rating,
  className,
}: MemoCardProps) {
  return (
    // The MemoList wraps a list of these in a single Accordion. Each card
    // is its own AccordionItem; the value is the ticker so the toolbar's
    // expand-all + anchor-scroll logic can target individual cards.
    <AccordionItem
      value={ticker}
      id={`memo-${ticker}`}
      data-ticker={ticker}
      data-testid={`memo-card-${ticker}`}
      className="border-b last:border-b-0"
    >
      <AccordionTrigger className="px-4 py-3 hover:no-underline">
        <div className="flex flex-1 items-center gap-3 flex-wrap text-left">
          <span
            className="font-mono text-sm font-semibold tracking-tight"
            data-testid="memo-summary-ticker"
          >
            {ticker}
          </span>
          {memo.thesis_one_liner && (
            <span className="text-sm text-muted-foreground line-clamp-1 max-w-md">
              {memo.thesis_one_liner}
            </span>
          )}
          <span className="ml-auto flex flex-wrap items-center gap-2 text-xs">
            {memo.conviction != null && <ConvictionBadge value={memo.conviction} />}
            {memo.thesis_alignment && <AlignmentBadge value={memo.thesis_alignment} />}
            {rating && <RatingBadge value={rating} />}
            {weakSpot?.current_pnl_pct != null && (
              <PnlPill value={weakSpot.current_pnl_pct} />
            )}
            <WeakSpotIcons spot={weakSpot} />
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-4 pb-4">
        <Card className={cn('shadow-none border bg-background', className)}>
          <CardContent className="space-y-4 py-4">
            {memo.reconciliation_notes && (
              <section className="rounded-md bg-muted/40 px-3 py-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Reconciliation notes
                </h3>
                <p className="mt-1 text-sm text-foreground/85">
                  {memo.reconciliation_notes}
                </p>
              </section>
            )}

            <EntityGrid memo={memo} />
            <ValuationTable valuation={memo.valuation} />
            <KeyNumbers items={memo.key_numbers} />
            <ThesisBreakers items={memo.thesis_breakers} />

            {ta && (
              <>
                <Separator />
                <section className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    TradingAgents debate
                  </h3>
                  <TaDebate ta={ta} />
                </section>
              </>
            )}
          </CardContent>
        </Card>
      </AccordionContent>
    </AccordionItem>
  );
}

function EntityGrid({ memo }: { memo: Memo }) {
  const blocks: { title: string; items: Entity[]; tone: 'good' | 'bad' | 'warn' }[] = [];
  if (memo.drivers?.length) {
    blocks.push({ title: 'Drivers', items: memo.drivers, tone: 'good' });
  }
  if (memo.risks?.length) {
    blocks.push({ title: 'Risks', items: memo.risks, tone: 'bad' });
  }
  if (memo.catalysts?.length) {
    blocks.push({ title: 'Catalysts', items: memo.catalysts, tone: 'warn' });
  }
  if (blocks.length === 0) return null;
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {blocks.map((block) => (
        <section key={block.title} className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {block.title}
          </h3>
          <ul className="space-y-2">
            {block.items.map((e, i) => (
              <li key={i} className="space-y-1 border-l-2 border-border pl-2.5">
                <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                  <span>{e.name ?? '(unnamed)'}</span>
                  {e.importance && (
                    <Badge variant="outline" className="font-normal">
                      {e.importance}
                    </Badge>
                  )}
                  {e.severity && (
                    <Badge variant="outline" className="font-normal">
                      severity {e.severity}
                    </Badge>
                  )}
                  {e.likelihood && (
                    <Badge variant="outline" className="font-normal">
                      likelihood {e.likelihood}
                    </Badge>
                  )}
                  {e.impact && (
                    <Badge variant="outline" className="font-normal">
                      impact {e.impact}
                    </Badge>
                  )}
                  {e.expected_window && (
                    <Badge variant="outline" className="font-normal">
                      window {e.expected_window}
                    </Badge>
                  )}
                </div>
                <EntityDescription description={e.description} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function EntityDescription({ description }: { description?: string | null }) {
  if (!description) return null;
  const PREVIEW_CUTOFF = 280;
  if (description.length <= PREVIEW_CUTOFF) {
    return <MdProse compact>{description}</MdProse>;
  }
  // Long-description tail. The Jinja UI rendered a 240-char preview *and*
  // a <details> with the full body, doubling up the lead-in. Replace with
  // a single Accordion that toggles between preview and full body.
  const preview = description.slice(0, 240).trimEnd();
  return (
    <Accordion type="single" collapsible className="w-full">
      <AccordionItem value="more" className="border-none">
        <div className="text-xs text-foreground/80 leading-relaxed">
          {preview}…
        </div>
        <AccordionTrigger
          className="py-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground hover:no-underline hover:text-foreground [&>svg]:size-3"
          data-testid="entity-show-more"
        >
          <span className="inline-flex items-center gap-1">
            show more
            <ChevronDown className="size-3" aria-hidden="true" />
          </span>
        </AccordionTrigger>
        <AccordionContent className="pb-2">
          <MdProse compact>{description}</MdProse>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

function ValuationTable({ valuation }: { valuation?: Memo['valuation'] }) {
  if (!valuation) return null;
  const rows = (['bear', 'base', 'bull', 'current'] as const)
    .map((label) => ({ label, row: valuation[label] }))
    .filter((r) => r.row);
  if (rows.length === 0) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Valuation
      </h3>
      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-muted/40">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium">Scenario</th>
              <th className="px-3 py-1.5 text-left font-medium">Price target</th>
              <th className="px-3 py-1.5 text-left font-medium">Methodology</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ label, row }) => (
              <tr key={label} className="border-t">
                <td className="px-3 py-1.5 font-medium capitalize">{label}</td>
                <td className="px-3 py-1.5 font-mono">
                  {row?.price_target != null ? `$${row.price_target.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-1.5 text-muted-foreground">
                  {row?.methodology ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function KeyNumbers({ items }: { items?: KeyNumber[] | null }) {
  if (!items?.length) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Key numbers
      </h3>
      <ul className="grid gap-1.5 text-sm sm:grid-cols-2">
        {items.map((k, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-1.5">
            <span className="font-medium">{k.label}:</span>
            <span className="font-mono">{k.value}</span>
            {k.unit && <span>{k.unit}</span>}
            {k.period && (
              <span className="text-xs text-muted-foreground">({k.period})</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ThesisBreakers({ items }: { items?: string[] | null }) {
  if (!items?.length) return null;
  return (
    <section className="rounded-md border border-bad/30 bg-bad-bg/40 px-3 py-2 space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-bad">
        Thesis breakers
      </h3>
      <p className="text-xs text-muted-foreground">
        If any of these happen, exit the position.
      </p>
      <ul className="space-y-1 text-sm">
        {items.map((b, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-bad" aria-hidden>
              ✕
            </span>
            <span>{b}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export type { Memo };
