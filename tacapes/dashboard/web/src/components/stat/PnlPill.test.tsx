import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PnlPill } from './PnlPill';

describe('PnlPill', () => {
  it.each([
    [6.7, 'good', '+6.7%'],
    [0.05, 'good', '+0.1%'],
    [0, 'neutral', '0.0%'],
    [-3.4, 'bad', '-3.4%'],
    [-22.78, 'bad', '-22.8%'],
  ])('value %f → variant %s, text %s', (value, variant, text) => {
    render(<PnlPill value={value} />);
    expect(screen.getByText(text).closest('[data-variant]')).toHaveAttribute(
      'data-variant',
      variant,
    );
  });

  it('null value renders em-dash as neutral', () => {
    render(<PnlPill value={null} />);
    const dash = screen.getByText('—');
    expect(dash.closest('[data-variant]')).toHaveAttribute('data-variant', 'neutral');
  });
});
