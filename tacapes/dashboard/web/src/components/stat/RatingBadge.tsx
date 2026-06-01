import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { ratingColor, semanticClasses } from '@/lib/derive';

interface RatingBadgeProps {
  value: string | null | undefined;
  className?: string;
}

/**
 * TradingAgents PortfolioRating chip:
 *   Buy / Overweight → good, Hold → warn, Underweight / Sell → bad.
 * Unknown ratings render as neutral with the raw value, so we surface
 * surprising values rather than hiding them.
 */
export function RatingBadge({ value, className }: RatingBadgeProps) {
  const color = ratingColor(value);
  const c = semanticClasses(color);
  const label = value || '—';
  return (
    <Badge
      variant="outline"
      data-variant={color}
      data-rating={value ?? ''}
      className={cn('font-medium', c.bg, c.text, c.border, className)}
    >
      <span className="sr-only">TA rating </span>
      {label}
    </Badge>
  );
}
