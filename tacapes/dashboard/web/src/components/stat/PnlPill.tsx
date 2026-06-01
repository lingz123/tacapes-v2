import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

import { cn } from '@/lib/utils';
import { pnlColor, semanticClasses } from '@/lib/derive';
import { pct } from '@/lib/format';

interface PnlPillProps {
  value: number | null | undefined;
  className?: string;
  /** Hide the arrow/dash glyph; useful in dense table cells. */
  noGlyph?: boolean;
}

/**
 * Colored P&L chip with arrow direction. Green up, red down, neutral dash
 * for zero or missing data. Uses mono digits so columns of pills line up.
 *
 * The spec hedges on a "real" sparkline (we only persist entry + current
 * prices), so this serves as the `<PnlArrow>` fallback called out in the
 * design's open questions section.
 */
export function PnlPill({ value, className, noGlyph }: PnlPillProps) {
  const color = pnlColor(value);
  const c = semanticClasses(color);
  const Icon = color === 'good' ? ArrowUpRight : color === 'bad' ? ArrowDownRight : Minus;
  return (
    <span
      data-variant={color}
      data-pnl={value ?? ''}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono tabular-nums',
        c.bg,
        c.text,
        c.border,
        className,
      )}
    >
      {!noGlyph && <Icon className="size-3" aria-hidden="true" />}
      <span className="sr-only">P&amp;L </span>
      {pct(value)}
    </span>
  );
}
