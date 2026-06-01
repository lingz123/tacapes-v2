import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { semanticClasses, type SemanticColor } from '@/lib/derive';
import type { MissionStatus } from '@/types/api';

interface StatusBadgeProps {
  status: MissionStatus;
  className?: string;
}

const STATUS_COLOR: Record<MissionStatus, SemanticColor> = {
  queued: 'neutral',
  running: 'warn',
  done: 'good',
  failed: 'bad',
};

const STATUS_LABEL: Record<MissionStatus, string> = {
  queued: 'queued',
  running: 'running',
  done: 'done',
  failed: 'failed',
};

/**
 * Small pill summarizing where a mission is in the pipeline. Mirrors the
 * Jinja `<span class="status">` chip but with shared semantic-color tokens
 * and a spinner for the `running` case.
 */
export function StatusBadge({ status, className }: StatusBadgeProps) {
  const color = STATUS_COLOR[status];
  const c = semanticClasses(color);
  return (
    <Badge
      variant="outline"
      data-variant={color}
      data-status={status}
      className={cn('font-medium', c.bg, c.text, c.border, className)}
    >
      {status === 'running' && <Loader2 className="size-3 mr-1 animate-spin" />}
      {STATUS_LABEL[status]}
    </Badge>
  );
}
