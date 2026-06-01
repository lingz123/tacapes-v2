import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MoreHorizontal, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { TableCell, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { StatusBadge } from './StatusBadge';
import { PnlPill } from '@/components/stat/PnlPill';
import { usd, relativeDate } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useDeleteMission } from '@/api/missions';
import type { MissionListItem } from '@/types/api';

interface MissionRowProps {
  mission: MissionListItem;
}

/**
 * One row in the mission list table. Whole-row click navigates to the
 * detail page; the trailing ⋯ button stops propagation so the menu trigger
 * doesn't accidentally also navigate.
 *
 * Delete shows a confirm Dialog. The Dialog dismisses on cancel/close
 * regardless of the mutation state so a user can back out at any time.
 */
export function MissionRow({ mission }: MissionRowProps) {
  const navigate = useNavigate();
  const del = useDeleteMission();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleDelete = async () => {
    try {
      await del.mutateAsync(mission.id);
      toast.success('Mission deleted');
      setConfirmOpen(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Could not delete mission';
      toast.error(msg);
    }
  };

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/40"
        onClick={() => navigate(`/missions/${mission.id}`)}
        data-testid="mission-row"
        data-mission-id={mission.id}
      >
        <TableCell className="py-3">
          <StatusBadge status={mission.status} />
        </TableCell>
        <TableCell className="py-3 max-w-md">
          <p className="line-clamp-2 text-sm">{mission.statement}</p>
        </TableCell>
        <TableCell className="py-3 text-xs text-muted-foreground whitespace-nowrap">
          {relativeDate(mission.created_at)}
        </TableCell>
        <TableCell className="py-3 text-xs text-muted-foreground whitespace-nowrap font-mono tabular-nums">
          {usd(mission.cost_usd, { cents: true })}
        </TableCell>
        <TableCell className="py-3 whitespace-nowrap">
          {mission.status === 'done' ? (
            <PnlPill value={mission.pnl_pct} />
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </TableCell>
        <TableCell className={cn('py-3 w-10 text-right')}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button
                size="sm"
                variant="ghost"
                aria-label="Row actions"
                data-testid="mission-row-menu"
              >
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              onClick={(e) => e.stopPropagation()}
            >
              <DropdownMenuItem
                onSelect={() => setConfirmOpen(true)}
                className="text-bad focus:text-bad"
                data-testid="mission-row-delete"
              >
                <Trash2 className="mr-2 size-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </TableCell>
      </TableRow>

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
              data-testid="mission-row-confirm-delete"
            >
              {del.isPending ? 'Deleting...' : 'Delete mission'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
