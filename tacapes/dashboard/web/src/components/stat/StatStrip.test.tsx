import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { StatStrip } from './StatStrip';

describe('StatStrip', () => {
  it('renders all tiles when every value is present', () => {
    render(
      <StatStrip
        tiles={[
          { label: 'Invested', value: '$20,000' },
          { label: 'Current', value: '$21,340' },
          { label: 'P&L', value: '+6.7%' },
          { label: 'Cash', value: '0%' },
        ]}
      />,
    );
    const strip = screen.getByTestId('stat-strip');
    expect(strip).toHaveAttribute('data-tile-count', '4');
    expect(screen.getByText('Invested')).toBeInTheDocument();
    expect(screen.getByText('$20,000')).toBeInTheDocument();
  });

  it('degrades to fewer tiles when fields are null', () => {
    render(
      <StatStrip
        tiles={[
          { label: 'Invested', value: '$10,000' },
          { label: 'Current', value: null },
          { label: 'P&L', value: undefined },
          { label: 'Positions', value: '3 of 5' },
        ]}
      />,
    );
    const strip = screen.getByTestId('stat-strip');
    expect(strip).toHaveAttribute('data-tile-count', '2');
    expect(screen.queryByText('Current')).not.toBeInTheDocument();
    expect(screen.queryByText('P&L')).not.toBeInTheDocument();
  });

  it('returns null when every tile is empty', () => {
    const { container } = render(
      <StatStrip
        tiles={[
          { label: 'Invested', value: null },
          { label: 'Current', value: '' },
        ]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
