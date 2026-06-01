import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RatingBadge } from './RatingBadge';

describe('RatingBadge', () => {
  it.each([
    ['Buy', 'good'],
    ['Overweight', 'good'],
    ['Hold', 'warn'],
    ['Underweight', 'bad'],
    ['Sell', 'bad'],
  ])('rating %s → %s', (value, variant) => {
    render(<RatingBadge value={value} />);
    expect(screen.getByText(value)).toHaveAttribute('data-variant', variant);
  });

  it('unknown rating reads as neutral, surfaces raw label', () => {
    render(<RatingBadge value="Mystery" />);
    expect(screen.getByText('Mystery')).toHaveAttribute('data-variant', 'neutral');
  });

  it('null renders neutral em-dash', () => {
    render(<RatingBadge value={null} />);
    expect(screen.getByText('—')).toHaveAttribute('data-variant', 'neutral');
  });
});
