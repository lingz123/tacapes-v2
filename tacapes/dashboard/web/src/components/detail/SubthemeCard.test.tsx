/**
 * Two of the plan's required cases for the audit-zone redesign:
 * - chosen-ratio rendering (dot row count + ratio label)
 * - missing-description fallback for backfilled missions
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SubthemeCard } from './SubthemeCard';
import type { SubthemeSummary } from '@/types/api';

function st(over: Partial<SubthemeSummary>): SubthemeSummary {
  return {
    id: 's1',
    name: 'AI Power',
    description: 'Nuclear positioned to absorb AI training load.',
    confidence: 0.7,
    candidate_count: 4,
    chosen_count: 2,
    chosen_tickers: ['NRG', 'BWXT'],
    passed_tickers: ['CCJ', 'UEC'],
    key_findings: ['Finding A', 'Finding B', 'Finding C ignored'],
    ...over,
  };
}

describe('<SubthemeCard>', () => {
  it('renders the chosen ratio dots: 2 filled + 2 hollow + "2/4 chosen"', () => {
    render(<SubthemeCard subtheme={st({})} />);
    const dotRow = screen.getByTestId('subtheme-dots');
    expect(dotRow.querySelectorAll('[data-dot="chosen"]')).toHaveLength(2);
    expect(dotRow.querySelectorAll('[data-dot="passed"]')).toHaveLength(2);
    expect(screen.getByText(/2\/4 chosen/)).toBeInTheDocument();
  });

  it('falls back to "no description recorded" when description is null', () => {
    render(<SubthemeCard subtheme={st({ description: null })} />);
    expect(screen.getByText(/no description recorded/i)).toBeInTheDocument();
  });

  it('shows only the first 2 key findings even if more were provided', () => {
    render(<SubthemeCard subtheme={st({})} />);
    expect(screen.getByText('Finding A')).toBeInTheDocument();
    expect(screen.getByText('Finding B')).toBeInTheDocument();
    expect(screen.queryByText('Finding C ignored')).toBeNull();
  });
});
