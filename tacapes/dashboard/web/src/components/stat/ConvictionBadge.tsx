import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { convictionColor, semanticClasses } from '@/lib/derive';

interface ConvictionBadgeProps {
  value: number | string | null | undefined;
  className?: string;
}

/**
 * Memo-writer conviction (1-5) as a colored chip. 4-5 reads green, 3 amber,
 * 1-2 red. Sets `data-variant` for tests and a small `data-conviction` for
 * downstream filtering. Pure function of input; no state, no effects.
 */
export function ConvictionBadge({ value, className }: ConvictionBadgeProps) {
  const color = convictionColor(value);
  const c = semanticClasses(color);
  const display = value == null || value === '' ? '—' : `${value}/5`;
  return (
    <Badge
      variant="outline"
      data-variant={color}
      data-conviction={value ?? ''}
      className={cn('font-mono', c.bg, c.text, c.border, className)}
    >
      <span className="sr-only">conviction </span>
      {display}
    </Badge>
  );
}
