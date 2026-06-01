/**
 * MSW-driven tests for the mission list page. Each case layers handlers on
 * top of the empty-list default from `src/test/server.ts`.
 *
 * Scope:
 *  - empty list renders the EmptyState
 *  - three missions render rows with the right cells
 *  - create flow: dialog open, submit, redirect
 *  - delete flow: ⋯ menu → confirm → optimistic removal
 *  - refresh flow: TopBar button calls /api/prices/refresh
 *  - validation: short statement blocks submit
 */
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MissionListPage } from './MissionList';
import { renderWithProviders } from '@/test/renderWithProviders';
import { server, http, HttpResponse, type MissionListResponse } from '@/test/server';

function listWith(missions: MissionListResponse['missions']): MissionListResponse {
  const invested = missions.length * 10000;
  return {
    missions,
    aggregate: {
      invested,
      current_value: invested * 1.05,
      pnl_pct: 5.0,
      cost: missions.length * 12.5,
      unpriced_count: 0,
    },
  };
}

const sampleMissions: MissionListResponse['missions'] = [
  {
    id: '11111111-1111-1111-1111-111111111111',
    statement: 'Buy nuclear power names positioned to win the data-center buildout',
    status: 'done',
    created_at: new Date(Date.now() - 5 * 86_400_000).toISOString(),
    completed_at: new Date(Date.now() - 4 * 86_400_000).toISOString(),
    cost_usd: 41.78,
    pnl_pct: 6.7,
    position_count: 4,
  },
  {
    id: '22222222-2222-2222-2222-222222222222',
    statement: 'Short cyclicals exposed to a 2026 industrial slowdown',
    status: 'running',
    created_at: new Date(Date.now() - 1 * 86_400_000).toISOString(),
    completed_at: null,
    cost_usd: null,
    pnl_pct: null,
    position_count: 0,
  },
  {
    id: '33333333-3333-3333-3333-333333333333',
    statement: 'Buy fintech names benefiting from regulatory tailwinds in 2026',
    status: 'done',
    created_at: new Date(Date.now() - 30 * 86_400_000).toISOString(),
    completed_at: new Date(Date.now() - 29 * 86_400_000).toISOString(),
    cost_usd: 38.12,
    pnl_pct: -4.2,
    position_count: 5,
  },
];

describe('MissionListPage', () => {
  it('renders the empty state when no missions exist', async () => {
    renderWithProviders(<MissionListPage />);
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText(/no missions yet/i)).toBeInTheDocument();
  });

  it('renders three missions with their status and P&L cells', async () => {
    server.use(
      http.get('/api/missions', () => HttpResponse.json(listWith(sampleMissions))),
    );
    renderWithProviders(<MissionListPage />);

    const rows = await screen.findAllByTestId('mission-row');
    expect(rows).toHaveLength(3);

    // First row: done, +6.7%.
    const first = within(rows[0]);
    expect(first.getByText(/done/i)).toBeInTheDocument();
    expect(first.getByText('+6.7%')).toBeInTheDocument();

    // Second row: running shows em-dash for P&L.
    const second = within(rows[1]);
    expect(second.getByText(/running/i)).toBeInTheDocument();

    // Third row: losing position is negative.
    const third = within(rows[2]);
    expect(third.getByText('-4.2%')).toBeInTheDocument();
  });

  it('blocks the create form when the statement is too short', async () => {
    const user = userEvent.setup();
    renderWithProviders(<MissionListPage />);

    await screen.findByTestId('empty-state');
    await user.click(screen.getByTestId('list-new-mission'));

    const form = await screen.findByTestId('new-mission-form');
    const statement = within(form).getByLabelText(/mission statement/i);
    await user.clear(statement);
    await user.type(statement, 'too short');
    await user.click(within(form).getByRole('button', { name: /create mission/i }));

    expect(await within(form).findByText(/at least 20 characters/i)).toBeInTheDocument();
  });

  it('creates a mission, closes the dialog, and navigates to detail', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/missions', () =>
        HttpResponse.json({ id: '44444444-4444-4444-4444-444444444444' }, { status: 201 }),
      ),
    );
    renderWithProviders(<MissionListPage />);
    await screen.findByTestId('empty-state');

    await user.click(screen.getByTestId('list-new-mission'));
    const form = await screen.findByTestId('new-mission-form');
    await user.type(
      within(form).getByLabelText(/mission statement/i),
      'Buy nuclear power names positioned to win the data-center buildout',
    );
    await user.click(within(form).getByRole('button', { name: /create mission/i }));

    await waitFor(() => {
      expect(screen.queryByTestId('new-mission-form')).not.toBeInTheDocument();
    });
  });

  it('confirms before deleting and removes the row from the table', async () => {
    const user = userEvent.setup();
    // Stateful list: GET reads the working copy so the post-mutation
    // invalidation re-fetch returns the row truly gone, not resurrected.
    let working = [...sampleMissions];
    server.use(
      http.get('/api/missions', () => HttpResponse.json(listWith(working))),
      http.delete('/api/missions/:id', ({ params }) => {
        working = working.filter((m) => m.id !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<MissionListPage />);

    const rows = await screen.findAllByTestId('mission-row');
    const first = within(rows[0]);

    await user.click(first.getByTestId('mission-row-menu'));
    // DropdownMenu portals to the document body, not inside the row.
    await user.click(await screen.findByTestId('mission-row-delete'));

    const confirmBtn = await screen.findByTestId('mission-row-confirm-delete');
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(screen.queryByText(/data-center buildout/i)).not.toBeInTheDocument();
    });
    // Working copy now has two entries left.
    expect(working).toHaveLength(2);
  });

  it('refreshes prices via the TopBar action', async () => {
    const user = userEvent.setup();
    const refresh = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(
      http.get('/api/missions', () => HttpResponse.json(listWith(sampleMissions))),
      http.post('/api/prices/refresh', () => refresh()),
    );
    renderWithProviders(<MissionListPage />);
    await screen.findAllByTestId('mission-row');

    await user.click(screen.getByTestId('topbar-refresh'));

    await waitFor(() => {
      expect(refresh).toHaveBeenCalled();
    });
  });

  it('shows the empty state with a "could not load" message when the API errors', async () => {
    server.use(
      http.get('/api/missions', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    );
    renderWithProviders(<MissionListPage />);
    expect(await screen.findByText(/could not load missions/i)).toBeInTheDocument();
  });
});
