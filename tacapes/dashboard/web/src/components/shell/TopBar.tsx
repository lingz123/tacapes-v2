import { Link } from 'react-router-dom';
import { Plus, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface TopBarProps {
  /** Optional callbacks for the right-side action buttons. */
  onNewMission?: () => void;
  onRefreshPrices?: () => void;
  /** Disable the refresh button while a refresh is in flight. */
  refreshing?: boolean;
  className?: string;
}

/**
 * App-wide top bar. Brand link on the left, two global actions on the right.
 * Sticky so the actions remain reachable when scrolling long mission detail
 * pages. Action buttons render as no-ops when no handler is wired (used for
 * placeholder pages before Phase 4 wires them up).
 */
export function TopBar({ onNewMission, onRefreshPrices, refreshing, className }: TopBarProps) {
  return (
    <header
      className={cn(
        'sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80',
        className,
      )}
    >
      <div className="container flex h-14 items-center justify-between gap-4">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="text-base">tacapes</span>
          <span className="text-2xs text-muted-foreground uppercase tracking-widest">
            research
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={onRefreshPrices}
            disabled={!onRefreshPrices || refreshing}
            data-testid="topbar-refresh"
          >
            <RefreshCw className={cn('size-4', refreshing && 'animate-spin')} />
            <span className="hidden sm:inline ml-2">Refresh prices</span>
          </Button>
          <Button
            size="sm"
            onClick={onNewMission}
            disabled={!onNewMission}
            data-testid="topbar-new-mission"
          >
            <Plus className="size-4" />
            <span className="hidden sm:inline ml-2">New mission</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
