import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { alignmentColor, alignmentLabel, semanticClasses } from '@/lib/derive';

interface AlignmentBadgeProps {
  value: string | null | undefined;
  className?: string;
}

/**
 * Memo-writer thesis alignment as a colored chip:
 *   aligned → good, fully_diverged → bad, *_divergence → warn.
 * Underscores stripped from the displayed label so it reads as prose.
 */
export function AlignmentBadge({ value, className }: AlignmentBadgeProps) {
  const color = alignmentColor(value);
  const c = semanticClasses(color);
  const label = alignmentLabel(value) || '—';
  return (
    <Badge
      variant="outline"
      data-variant={color}
      data-alignment={value ?? ''}
      className={cn('font-normal', c.bg, c.text, c.border, className)}
    >
      <span className="sr-only">thesis alignment </span>
      {label}
    </Badge>
  );
}
