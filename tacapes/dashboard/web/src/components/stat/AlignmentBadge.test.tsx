import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AlignmentBadge } from './AlignmentBadge';

describe('AlignmentBadge', () => {
  it.each([
    ['aligned', 'good'],
    ['fully_diverged', 'bad'],
    ['partial_divergence', 'warn'],
    ['minor_divergence', 'warn'],
  ])('alignment %s → %s', (value, variant) => {
    render(<AlignmentBadge value={value} />);
    // alignmentLabel strips underscores; query by the un-underscored text.
    const label = value.replace(/_/g, ' ');
    expect(screen.getByText(label)).toHaveAttribute('data-variant', variant);
  });

  it('null renders neutral em-dash', () => {
    render(<AlignmentBadge value={null} />);
    expect(screen.getByText('—')).toHaveAttribute('data-variant', 'neutral');
  });

  it('unknown values fall back to neutral', () => {
    render(<AlignmentBadge value="rocketship" />);
    expect(screen.getByText('rocketship')).toHaveAttribute('data-variant', 'neutral');
  });
});
