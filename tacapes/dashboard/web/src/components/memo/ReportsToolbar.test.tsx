/**
 * Sort + filter behaviour through URL search params, plus the
 * expand-all / collapse-all callbacks.
 *
 * The toolbar leans on react-router-dom's useSearchParams, so the tests
 * mount it under a MemoryRouter rooted at a URL with the params we want
 * to assert on.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { ReportsToolbar } from './ReportsToolbar';

function LocationProbe({ onChange }: { onChange: (search: string) => void }) {
  const loc = useLocation();
  onChange(loc.search);
  return null;
}

function withRouter(
  ui: React.ReactNode,
  { initial = '/?' }: { initial?: string } = {},
) {
  return render(<MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>);
}

describe('<ReportsToolbar>', () => {
  it('writes sort to URL search params when not the default', () => {
    let search = '';
    withRouter(
      <>
        <ReportsToolbar onExpandAll={vi.fn()} onCollapseAll={vi.fn()} />
        <LocationProbe onChange={(s) => (search = s)} />
      </>,
    );

    // Open the select. Radix uses a hidden native select for jsdom paths,
    // and we exposed `data-testid` on items. Use the keyboard-flow instead.
    const trigger = screen.getByTestId('sort-select');
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(screen.getByRole('option', { name: 'P&L' }));

    expect(search).toContain('sort=pnl');
  });

  it('drops the sort param when reverting to the default (portfolio)', () => {
    let search = '';
    withRouter(
      <>
        <ReportsToolbar onExpandAll={vi.fn()} onCollapseAll={vi.fn()} />
        <LocationProbe onChange={(s) => (search = s)} />
      </>,
      { initial: '/?sort=conviction' },
    );

    const trigger = screen.getByTestId('sort-select');
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(screen.getByRole('option', { name: 'Portfolio order' }));

    expect(search).not.toContain('sort=');
  });

  it('filter chips are mutually exclusive: clicking trap replaces fallback', () => {
    let search = '';
    withRouter(
      <>
        <ReportsToolbar onExpandAll={vi.fn()} onCollapseAll={vi.fn()} />
        <LocationProbe onChange={(s) => (search = s)} />
      </>,
      { initial: '/?filter=fallback' },
    );

    fireEvent.click(screen.getByTestId('filter-trap'));
    expect(search).toContain('filter=trap');
    expect(search).not.toContain('fallback');
  });

  it('expand-all and collapse-all fire callbacks', () => {
    const onExpandAll = vi.fn();
    const onCollapseAll = vi.fn();
    withRouter(
      <ReportsToolbar onExpandAll={onExpandAll} onCollapseAll={onCollapseAll} />,
    );
    fireEvent.click(screen.getByTestId('expand-all'));
    fireEvent.click(screen.getByTestId('collapse-all'));
    expect(onExpandAll).toHaveBeenCalled();
    expect(onCollapseAll).toHaveBeenCalled();
  });
});
