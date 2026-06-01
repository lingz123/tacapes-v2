import { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';

import { AppShell } from '@/components/shell/AppShell';
import { EmptyState } from '@/components/shell/EmptyState';
import { StatStrip } from '@/components/stat/StatStrip';
import { PnlPill } from '@/components/stat/PnlPill';
import { MissionRow } from '@/components/mission/MissionRow';
import { NewMissionDialog } from '@/components/mission/NewMissionDialog';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useMissionList, useRefreshPrices } from '@/api/missions';
import { usd, pct } from '@/lib/format';
import { pnlColor } from '@/lib/derive';

/**
 * Mission index page. Three vertical sections: header aggregate stats,
 * action bar, table of missions. Loading shows a tall skeleton stack so
 * the layout doesn't jump when the data lands.
 */
export function MissionListPage() {
  const { data, isLoading, isError, error } = useMissionList();
  const refresh = useRefreshPrices();
  const [newOpen, setNewOpen] = useState(false);

  const handleRefresh = async () => {
    try {
      await refresh.mutateAsync();
      toast.success('Prices refreshed');
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Could not refresh prices';
      toast.error(msg);
    }
  };

  const aggregate = data?.aggregate;
  const tiles = aggregate
    ? [
        { label: 'Invested', value: usd(aggregate.invested) },
        { label: 'Current', value: usd(aggregate.current_value) },
        {
          label: 'P&L',
          value: pct(aggregate.pnl_pct),
          accent: pnlColor(aggregate.pnl_pct),
          delta: aggregate.pnl_pct == null ? undefined : (
            <PnlPill value={aggregate.pnl_pct} noGlyph />
          ),
        },
        { label: 'Spent', value: usd(aggregate.cost, { cents: true }) },
        {
          label: 'Unpriced',
          value: aggregate.unpriced_count > 0 ? aggregate.unpriced_count : null,
        },
      ]
    : [];

  return (
    <AppShell
      onNewMission={() => setNewOpen(true)}
      onRefreshPrices={handleRefresh}
      refreshing={refresh.isPending}
    >
      <header className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Missions</h1>
          <p className="text-sm text-muted-foreground">
            All-time results across every backfilled and run mission.
          </p>
        </div>
        {aggregate && <StatStrip tiles={tiles} />}
      </header>

      <section className="mt-6 flex items-center justify-end gap-2">
        {/*
          TopBar already exposes New mission and Refresh prices, but a duplicate
          here keeps the primary action discoverable for first-time users
          looking at the table directly.
        */}
        <Button size="sm" onClick={() => setNewOpen(true)} data-testid="list-new-mission">
          <Plus className="size-4 mr-2" />
          New mission
        </Button>
      </section>

      <section className="mt-3">
        {isLoading && <ListSkeleton />}
        {isError && (
          <EmptyState
            title="Could not load missions"
            description={
              error instanceof Error ? error.message : 'Unknown error talking to the API.'
            }
          />
        )}
        {data && data.missions.length === 0 && (
          <EmptyState
            title="No missions yet"
            description="Define a mandate and let the pipeline shortlist names. The result lands here."
            action={
              <Button onClick={() => setNewOpen(true)}>
                <Plus className="size-4 mr-2" />
                New mission
              </Button>
            }
          />
        )}
        {data && data.missions.length > 0 && (
          <div className="rounded-lg border bg-card shadow-sm overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">Status</TableHead>
                  <TableHead>Statement</TableHead>
                  <TableHead className="w-32 whitespace-nowrap">Created</TableHead>
                  <TableHead className="w-24 whitespace-nowrap">Cost</TableHead>
                  <TableHead className="w-28 whitespace-nowrap">P&amp;L</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.missions.map((m) => (
                  <MissionRow key={m.id} mission={m} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <NewMissionDialog open={newOpen} onOpenChange={setNewOpen} />
    </AppShell>
  );
}

/** Reduces layout jump while the first request is in flight. */
function ListSkeleton() {
  return (
    <div className="space-y-2" data-testid="list-skeleton">
      {Array.from({ length: 3 }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}
