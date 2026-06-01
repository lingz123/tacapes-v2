/**
 * Mission detail page (Phase 5).
 *
 * Three vertical zones per the redesign spec §5:
 *   A · Outcome  — position table, scan-first
 *   B · Why      — sub-themes + shortlist (Phase 5 day 2)
 *   C · Audit    — memo accordion + TA debate + toolbar (Phase 5 day 2)
 *
 * Status branching: `done` shows the full layout; `queued`/`running` shows a
 * skeleton with a spinner; `failed` shows a panel surfacing the error and a
 * delete affordance. Polling is delegated to `useMissionStatus` — its
 * `refetchInterval` is null once the mission lands.
 */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ChevronLeft, Loader2, MoreHorizontal, Trash2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

import { AppShell } from '@/components/shell/AppShell';
import { EmptyState } from '@/components/shell/EmptyState';
import { StatStrip, type StatTileProps } from '@/components/stat/StatStrip';
import { PnlPill } from '@/components/stat/PnlPill';
import { PositionsTable } from '@/components/detail/PositionsTable';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useDeleteMission,
  useMissionDetail,
  useMissionStatus,
  useRefreshPrices,
} from '@/api/missions';
import { pnlColor } from '@/lib/derive';
import { pct, relativeDate, usd } from '@/lib/format';
import type { MissionDetail, StatStripShape } from '@/types/api';

function tilesFromStripStat(stat: StatStripShape): StatTileProps[] {
  return [
    { label: 'Invested', value: usd(stat.invested) },
    { label: 'Current', value: usd(stat.current_value) },
    {
      label: 'P&L',
      value: pct(stat.pnl_pct),
      accent: pnlColor(stat.pnl_pct),
      delta:
        stat.pnl_usd == null ? undefined : (
          <span className="text-xs font-mono text-muted-foreground">{usd(stat.pnl_usd)}</span>
        ),
    },
    {
      label: 'Cash',
      value: `${(stat.cash_reserve_pct * 100).toFixed(0)}%`,
    },
    {
      label: 'Positions',
      value: `${stat.position_count} of ${stat.position_count}`,
    },
    {
      label: 'Unpriced',
      value: stat.unpriced_count > 0 ? stat.unpriced_count : null,
    },
  ];
}

export function MissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const detail = useMissionDetail(id);
  // Status polls independently so the heavy detail query isn't repeated on
  // every tick. Once `done` lands, the polling hook invalidates the detail
  // cache so the body re-renders with the full payload.
  const status = useMissionStatus(id);
  const refresh = useRefreshPrices();
  const navigate = useNavigate();
  const del = useDeleteMission();
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Prefer the status endpoint when the detail payload predates it (typical
  // for the first render); otherwise the detail's own status is fine.
  const effectiveStatus = status.data?.status ?? detail.data?.status;

  const handleRefresh = async () => {
    try {
      await refresh.mutateAsync();
      toast.success('Prices refreshed');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not refresh prices');
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    try {
      await del.mutateAsync(id);
      toast.success('Mission deleted');
      navigate('/');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not delete mission');
    }
  };

  return (
    <AppShell onRefreshPrices={handleRefresh} refreshing={refresh.isPending}>
      <nav className="text-xs">
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="size-3" />
          All missions
        </Link>
      </nav>

      {detail.isLoading && <DetailSkeleton />}
      {detail.isError && (
        <EmptyState
          title="Could not load mission"
          description={
            detail.error instanceof Error ? detail.error.message : 'Unknown error.'
          }
        />
      )}

      {detail.data && (
        <>
          <DetailHeader
            mission={detail.data}
            onDelete={() => setConfirmOpen(true)}
          />

          {effectiveStatus === 'queued' || effectiveStatus === 'running' ? (
            <RunningPanel status={effectiveStatus} />
          ) : effectiveStatus === 'failed' ? (
            <FailedPanel
              error={detail.data.error_message ?? status.data?.error_message ?? null}
              onDelete={() => setConfirmOpen(true)}
            />
          ) : (
            <DoneBody mission={detail.data} />
          )}
        </>
      )}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this mission?</DialogTitle>
            <DialogDescription>
              The mission, its stage outputs, and any backfilled portfolio files are
              removed permanently. Running missions cannot be deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={del.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={del.isPending}
              data-testid="detail-confirm-delete"
            >
              {del.isPending ? 'Deleting...' : 'Delete mission'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}

function DetailHeader({
  mission,
  onDelete,
}: {
  mission: MissionDetail;
  onDelete: () => void;
}) {
  const tiles = mission.stat_strip ? tilesFromStripStat(mission.stat_strip) : [];
  return (
    <header className="mt-2 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <h1
          className="text-2xl font-semibold tracking-tight leading-snug max-w-3xl"
          data-testid="detail-statement"
        >
          {mission.statement}
        </h1>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="sm"
              variant="ghost"
              aria-label="Mission actions"
              data-testid="detail-actions"
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={onDelete}
              className="text-bad focus:text-bad"
              data-testid="detail-delete"
            >
              <Trash2 className="mr-2 size-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {tiles.length > 0 && <StatStrip tiles={tiles} />}

      <p className="text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
        <span>{mission.horizon_months}mo horizon</span>
        <span aria-hidden>·</span>
        <span>budget {usd(mission.budget_usd)}</span>
        {mission.cost_usd != null && (
          <>
            <span aria-hidden>·</span>
            <span>{usd(mission.cost_usd, { cents: true })} spent</span>
          </>
        )}
        <span aria-hidden>·</span>
        <span>created {relativeDate(mission.created_at)}</span>
        {mission.stat_strip && mission.stat_strip.pnl_pct != null && (
          <>
            <span aria-hidden>·</span>
            <span className="inline-flex items-center gap-1">
              All-in P&L <PnlPill value={mission.stat_strip.pnl_pct} noGlyph />
            </span>
          </>
        )}
      </p>
    </header>
  );
}

function DoneBody({ mission }: { mission: MissionDetail }) {
  return (
    <div className="mt-8 space-y-10" data-testid="detail-done">
      <Zone title="Outcome" subtitle="What's working, what's not.">
        <PositionsTable positions={mission.positions} />
      </Zone>

      <Zone
        title="Why"
        subtitle="The thesis tree and which candidates made the cut."
      >
        <p
          className="text-sm text-muted-foreground italic"
          data-testid="zone-why-placeholder"
        >
          Sub-themes and shortlist land in Phase 5 day 2.
        </p>
      </Zone>

      <Zone
        title="Audit"
        subtitle="Per-ticker reports with weak-spot flags."
      >
        <p
          className="text-sm text-muted-foreground italic"
          data-testid="zone-audit-placeholder"
        >
          Memo accordion + TA debate land in Phase 5 day 2.
        </p>
      </Zone>
    </div>
  );
}

function Zone({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
        <Separator className="!mt-2" />
      </div>
      {children}
    </section>
  );
}

function RunningPanel({ status }: { status: 'queued' | 'running' }) {
  return (
    <Card className="mt-6" data-testid="detail-running">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-foreground">
          {status === 'queued'
            ? 'Mission is queued. The runner picks it up in a moment.'
            : 'Pipeline running. The page refreshes itself when it lands.'}
        </p>
        <p className="text-xs text-muted-foreground">
          Polling every 3 seconds.
        </p>
      </CardContent>
    </Card>
  );
}

function FailedPanel({
  error,
  onDelete,
}: {
  error: string | null;
  onDelete: () => void;
}) {
  return (
    <Card className="mt-6 border-bad/40" data-testid="detail-failed">
      <CardContent className="flex flex-col items-start gap-3 py-6">
        <div className="flex items-center gap-2 text-bad">
          <AlertTriangle className="size-4" />
          <h2 className="text-base font-semibold">Mission failed</h2>
        </div>
        {error ? (
          <pre className="w-full whitespace-pre-wrap text-xs font-mono text-foreground bg-muted rounded-md p-3">
            {error}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground">
            The pipeline exited with no recorded reason. Re-run from the CLI to
            collect a full traceback.
          </p>
        )}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onDelete}>
            <Trash2 className="mr-2 size-3" />
            Delete mission
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DetailSkeleton() {
  return (
    <div className="mt-4 space-y-6" data-testid="detail-skeleton">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}
