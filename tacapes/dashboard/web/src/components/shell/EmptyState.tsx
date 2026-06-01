import { ReactNode } from 'react';

import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  /** Primary call-to-action; usually a Button. */
  action?: ReactNode;
  className?: string;
}

/**
 * Generic empty-state card. Used as the zero-missions placeholder on the
 * list page and any other "nothing here yet" zone we add later.
 * Intentionally minimal so the call-to-action carries the visual weight.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <Card className={cn('mt-6 border-dashed shadow-none', className)} data-testid="empty-state">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        {icon && <div className="text-muted-foreground">{icon}</div>}
        <h3 className="text-base font-semibold tracking-tight">{title}</h3>
        {description && (
          <p className="max-w-md text-sm text-muted-foreground">{description}</p>
        )}
        {action && <div className="mt-2">{action}</div>}
      </CardContent>
    </Card>
  );
}
