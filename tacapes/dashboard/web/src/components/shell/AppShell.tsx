import { ReactNode } from 'react';

import { TopBar } from './TopBar';
import { cn } from '@/lib/utils';

interface AppShellProps {
  children: ReactNode;
  /** Per-route handlers wired through to the TopBar. */
  onNewMission?: () => void;
  onRefreshPrices?: () => void;
  refreshing?: boolean;
  className?: string;
}

/**
 * Page-level shell: sticky TopBar over a centered container. Pages render
 * their own header/content inside this. Keeps the chrome owned in one place
 * so adding a sidebar or breadcrumb only touches AppShell.
 */
export function AppShell({
  children,
  onNewMission,
  onRefreshPrices,
  refreshing,
  className,
}: AppShellProps) {
  return (
    <div className={cn('min-h-screen bg-background text-foreground', className)}>
      <TopBar
        onNewMission={onNewMission}
        onRefreshPrices={onRefreshPrices}
        refreshing={refreshing}
      />
      <main className="container py-6">{children}</main>
    </div>
  );
}
