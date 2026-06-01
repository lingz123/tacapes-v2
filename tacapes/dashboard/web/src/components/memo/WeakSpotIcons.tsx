/**
 * Tiny icon row that surfaces the three weak-spot flags from
 * `MissionDetail.weak_spots`. Renders in memo summary rows so the user can
 * scan a long mission and find the names worth scrutinizing without opening
 * every accordion.
 *
 * Glyphs match the spec's filter chips: ⚠ fallback, ⚖ momentum trap, 📉 losing.
 * Each glyph carries a Tooltip explaining what triggered it.
 */
import { AlertTriangle, Scale, TrendingDown } from 'lucide-react';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { WeakSpot } from '@/types/api';

interface WeakSpotIconsProps {
  spot: WeakSpot | null | undefined;
  className?: string;
}

export function WeakSpotIcons({ spot, className }: WeakSpotIconsProps) {
  if (!spot) return null;
  const items = [
    spot.is_fallback_memo && {
      key: 'fallback',
      Icon: AlertTriangle,
      colorClass: 'text-warn',
      tip: 'Memo writer fell back to a deterministic shape. Likely missing prose.',
    },
    spot.is_momentum_trap && {
      key: 'trap',
      Icon: Scale,
      colorClass: 'text-warn',
      tip: 'Conviction 3 + thesis diverged. The matrix collapses here when TA and thesis disagree.',
    },
    spot.is_losing && {
      key: 'losing',
      Icon: TrendingDown,
      colorClass: 'text-bad',
      tip: 'Position is down since entry. Worth a closer look at the catalysts.',
    },
  ].filter(Boolean) as Array<{
    key: string;
    Icon: typeof AlertTriangle;
    colorClass: string;
    tip: string;
  }>;

  if (items.length === 0) return null;

  return (
    <TooltipProvider delayDuration={150}>
      <span
        className={cn('inline-flex items-center gap-1', className)}
        data-testid="weak-spot-icons"
        data-flags={items.map((i) => i.key).join(' ')}
      >
        {items.map(({ key, Icon, colorClass, tip }) => (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <span
                className={cn('inline-flex', colorClass)}
                aria-label={tip}
                data-flag={key}
              >
                <Icon className="size-3.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs text-xs">
              {tip}
            </TooltipContent>
          </Tooltip>
        ))}
      </span>
    </TooltipProvider>
  );
}
