import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ConvictionBadge } from './ConvictionBadge';

// One assertion per row: matrix of inputs covering both color bands and the
// missing-value placeholder. Mirrors the conviction_color filter in
// tacapes/dashboard/filters.py; if these diverge in Phase 6+, we want the
// frontend test, not a dogfood pass, to catch it.
describe('ConvictionBadge', () => {
  it.each([
    [5, 'good'],
    [4, 'good'],
    [3, 'warn'],
    [2, 'bad'],
    [1, 'bad'],
  ])('conviction %d → %s', (value, variant) => {
    render(<ConvictionBadge value={value} />);
    expect(screen.getByText(`${value}/5`)).toHaveAttribute('data-variant', variant);
  });

  it('null value renders the em-dash placeholder as neutral', () => {
    render(<ConvictionBadge value={null} />);
    const badge = screen.getByText('—');
    expect(badge).toHaveAttribute('data-variant', 'neutral');
  });

  it('non-numeric strings render as neutral', () => {
    render(<ConvictionBadge value="banana" />);
    expect(screen.getByText('banana/5')).toHaveAttribute('data-variant', 'neutral');
  });
});
