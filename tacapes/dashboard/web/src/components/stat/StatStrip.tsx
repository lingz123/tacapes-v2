import { ReactNode } from 'react';

import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { semanticClasses, type SemanticColor } from '@/lib/derive';

export interface StatTileProps {
  label: string;
  /** Already-formatted value text (e.g. "$21,340"). null/undefined → tile is skipped entirely. */
  value: ReactNode | null | undefined;
  /** Optional secondary line under the value: usually a PnlPill or a tiny meta string. */
  delta?: ReactNode;
  /** Optional color accent for the value (used for the P&L tile). */
  accent?: SemanticColor;
}

interface StatStripProps {
  tiles: StatTileProps[];
  className?: string;
}

/**
 * Horizontal strip of stat cards. Pure presentational: filter empty tiles
 * up-front so a missing-stat-strip (mission still running, or zero positions)
 * collapses to whatever subset has data rather than rendering "—" placeholders.
 *
 * Tiles wrap on small screens via `flex-wrap`, then sit one-per-row at ≤640px.
 * Accent is applied only to the value text so labels stay neutral.
 */
export function StatStrip({ tiles, className }: StatStripProps) {
  const visible = tiles.filter((tile) => tile.value != null && tile.value !== '');
  if (visible.length === 0) return null;

  return (
    <div
      data-testid="stat-strip"
      data-tile-count={visible.length}
      className={cn('flex flex-wrap gap-3', className)}
    >
      {visible.map((tile) => {
        const accentClass = tile.accent ? semanticClasses(tile.accent).text : 'text-foreground';
        return (
          <Card
            key={tile.label}
            className="flex-1 min-w-[140px] px-4 py-3 shadow-sm"
            data-tile={tile.label}
          >
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {tile.label}
            </p>
            <p
              className={cn(
                'mt-1 text-xl font-semibold font-mono tabular-nums leading-tight',
                accentClass,
              )}
            >
              {tile.value}
            </p>
            {tile.delta != null && <div className="mt-1">{tile.delta}</div>}
          </Card>
        );
      })}
    </div>
  );
}
