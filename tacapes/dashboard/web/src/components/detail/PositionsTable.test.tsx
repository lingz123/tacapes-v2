/**
 * Sort + link behaviour for the Outcome zone's position table.
 *
 * Two of the cases here are the ones the plan explicitly calls out
 * (P&L default sort and ticker-cell memo anchors). The third pins the
 * empty-state path so backfilled / pre-positions missions don't crash.
 */
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import { PositionsTable } from './PositionsTable';
import type { PositionPnl } from '@/types/api';

function pos(over: Partial<PositionPnl>): PositionPnl {
  return {
    ticker: 'NRG',
    weight_pct: 0.25,
    notional_usd: 5000,
    rationale: null,
    entry_price: 100,
    entry_price_date: '2026-05-12',
    current_price: 110,
    pnl_pct: 10,
    ...over,
  };
}

describe('<PositionsTable>', () => {
  it('defaults to P&L descending so winners sit first', () => {
    const positions = [
      pos({ ticker: 'CCJ', pnl_pct: -4 }),
      pos({ ticker: 'NRG', pnl_pct: 18 }),
      pos({ ticker: 'BWXT', pnl_pct: 6 }),
      // unpriced sinks to bottom on desc
      pos({ ticker: 'UEC', pnl_pct: null, current_price: null }),
    ];
    render(<PositionsTable positions={positions} />);
    const order = screen
      .getAllByTestId(/^position-memo-link-/)
      .map((el) => el.textContent);
    expect(order).toEqual(['NRG', 'BWXT', 'CCJ', 'UEC']);
  });

  it('ticker cell links to the matching memo anchor', () => {
    render(<PositionsTable positions={[pos({ ticker: 'NRG' })]} />);
    const link = screen.getByTestId('position-memo-link-NRG');
    expect(link.getAttribute('href')).toBe('#memo-NRG');
  });

  it('header click flips the sort direction', () => {
    const positions = [
      pos({ ticker: 'A', pnl_pct: 5 }),
      pos({ ticker: 'B', pnl_pct: 10 }),
      pos({ ticker: 'C', pnl_pct: 1 }),
    ];
    render(<PositionsTable positions={positions} />);
    const pnlHeader = screen.getByRole('button', { name: /P&L/ });
    // Default desc: 10, 5, 1
    let order = screen
      .getAllByTestId(/^position-memo-link-/)
      .map((el) => el.textContent);
    expect(order).toEqual(['B', 'A', 'C']);
    fireEvent.click(pnlHeader); // flip to asc
    order = screen.getAllByTestId(/^position-memo-link-/).map((el) => el.textContent);
    expect(order).toEqual(['C', 'A', 'B']);
  });

  it('renders an empty-state message when there are no positions', () => {
    render(<PositionsTable positions={[]} />);
    expect(screen.queryByTestId('positions-table')).toBeNull();
    expect(screen.getByText(/no positions recorded/i)).toBeInTheDocument();
  });

  it('shows the entry date under the entry price', () => {
    render(
      <PositionsTable
        positions={[pos({ ticker: 'NRG', entry_price_date: '2026-05-12' })]}
      />,
    );
    const row = screen.getByTestId('position-memo-link-NRG').closest('tr')!;
    expect(within(row).getByText('2026-05-12')).toBeInTheDocument();
  });
});
