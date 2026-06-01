/**
 * Shortlist table behaviour: conviction comes from the memo lookup, primary
 * sub-theme attribution prefers the memo's singular `subtheme_id` and falls
 * back to `candidate.sub_theme_ids[0]` for shortlist-only names. These
 * cases were surfaced by the Phase 7 dogfood pass — backfilled missions
 * don't carry conviction or `sub_theme_id` on shortlist rows.
 */
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { ShortlistTable, type ShortlistCandidate } from './ShortlistTable';

function cand(over: Partial<ShortlistCandidate>): ShortlistCandidate {
  return { ticker: 'NRG', sub_theme_ids: ['nuclear'], why_relevant: null, ...over };
}

describe('<ShortlistTable>', () => {
  it('pulls conviction from the per-ticker memo lookup', () => {
    render(
      <ShortlistTable
        candidates={[cand({ ticker: 'NRG' })]}
        chosen={['NRG']}
        subthemeNames={{ nuclear: 'Nuclear operators' }}
        convictionByTicker={{ NRG: 4 }}
      />,
    );
    const row = screen.getByTestId('shortlist-memo-link-NRG').closest('tr')!;
    expect(within(row).getByText('4/5')).toBeInTheDocument();
  });

  it('renders a dash when conviction is missing for a ticker', () => {
    render(
      <ShortlistTable
        candidates={[cand({ ticker: 'NRG' })]}
        chosen={[]}
        convictionByTicker={{}}
      />,
    );
    const row = screen.getByTestId('shortlist-memo-link-NRG').closest('tr')!;
    expect(within(row).getByText('—')).toBeInTheDocument();
  });

  it('prefers memo.subtheme_id for attribution when present', () => {
    render(
      <ShortlistTable
        candidates={[cand({ ticker: 'NRG', sub_theme_ids: ['theme-a', 'theme-b'] })]}
        chosen={[]}
        subthemeNames={{ 'theme-a': 'Theme A', 'theme-b': 'Theme B' }}
        primarySubthemeByTicker={{ NRG: 'theme-b' }}
      />,
    );
    expect(screen.getByText('Theme B')).toBeInTheDocument();
    expect(screen.queryByText('Theme A')).toBeNull();
  });

  it('falls back to sub_theme_ids[0] when the memo lookup is absent', () => {
    render(
      <ShortlistTable
        candidates={[cand({ ticker: 'NRG', sub_theme_ids: ['theme-a', 'theme-b'] })]}
        chosen={[]}
        subthemeNames={{ 'theme-a': 'Theme A', 'theme-b': 'Theme B' }}
      />,
    );
    expect(screen.getByText('Theme A')).toBeInTheDocument();
  });

  it('shows the chosen pill for tickers in the portfolio', () => {
    render(
      <ShortlistTable
        candidates={[
          cand({ ticker: 'NRG' }),
          cand({ ticker: 'CCJ' }),
        ]}
        chosen={['NRG']}
      />,
    );
    const nrgRow = screen.getByTestId('shortlist-memo-link-NRG').closest('tr')!;
    const ccjRow = screen.getByTestId('shortlist-memo-link-CCJ').closest('tr')!;
    expect(within(nrgRow).getByText('Chosen')).toBeInTheDocument();
    expect(within(ccjRow).getByText('Passed')).toBeInTheDocument();
  });
});
