/**
 * MemoCard summary-row contract:
 *   - ticker anchor target sits on the AccordionItem so #memo-XYZ scrolls
 *     to the right card.
 *   - badges + WeakSpotIcons + PnlPill render when the corresponding fields
 *     are present.
 *   - Long descriptions render as a "show more" tail (no duplicate preview
 *     + full-body block).
 *   - Fallback warning is NOT in the card body any more — it lives in the
 *     summary via WeakSpotIcons.
 */
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { Accordion } from '@/components/ui/accordion';
import { MemoCard, type Memo } from './MemoCard';
import type { WeakSpot } from '@/types/api';

function withAccordion(
  children: React.ReactNode,
  { defaultValue }: { defaultValue?: string[] } = {},
) {
  return render(
    <Accordion type="multiple" defaultValue={defaultValue}>
      {children}
    </Accordion>,
  );
}

describe('<MemoCard>', () => {
  const memo: Memo = {
    ticker: 'NRG',
    thesis_one_liner: 'Nuclear utility positioned for AI-load tailwind.',
    conviction: 4,
    thesis_alignment: 'aligned',
    drivers: [{ name: 'AI load growth', description: 'Short blurb.' }],
    risks: [{ name: 'Regulatory', description: 'Short blurb.' }],
    catalysts: null,
    reconciliation_notes: 'TA and thesis align on the upside.',
  };

  it('AccordionItem has id `memo-NRG` so anchor scroll works', () => {
    const { container } = withAccordion(
      <MemoCard ticker="NRG" memo={memo} />,
    );
    expect(container.querySelector('#memo-NRG')).not.toBeNull();
  });

  it('summary row renders conviction + alignment + rating badges', () => {
    withAccordion(<MemoCard ticker="NRG" memo={memo} rating="Buy" />);
    const card = screen.getByTestId('memo-card-NRG');
    // Conviction badge ships data-variant. 4 → good.
    const conv = within(card).getByText('4/5');
    expect(conv.closest('[data-variant]')?.getAttribute('data-variant')).toBe('good');
    // Alignment + rating both show.
    expect(within(card).getByText('aligned')).toBeInTheDocument();
    expect(within(card).getByText('Buy')).toBeInTheDocument();
  });

  it('renders WeakSpotIcons in the summary when flags are set', () => {
    const spot: WeakSpot = {
      ticker: 'NRG',
      is_fallback_memo: true,
      is_momentum_trap: false,
      is_losing: true,
      current_pnl_pct: -4.2,
    };
    withAccordion(<MemoCard ticker="NRG" memo={memo} weakSpot={spot} />);
    const icons = screen.getByTestId('weak-spot-icons');
    expect(icons.getAttribute('data-flags')).toContain('fallback');
    expect(icons.getAttribute('data-flags')).toContain('losing');
    expect(icons.getAttribute('data-flags')).not.toContain('trap');
  });

  it('long entity descriptions render as a "show more" tail', () => {
    const longText = 'lorem ipsum dolor sit amet, '.repeat(20);
    const memoLong: Memo = {
      drivers: [{ name: 'Long driver', description: longText }],
    };
    // Mount with the card already expanded so the inner accordion's
    // "show more" trigger is mounted (Radix only mounts open AccordionContent).
    withAccordion(<MemoCard ticker="LONG" memo={memoLong} />, {
      defaultValue: ['LONG'],
    });
    expect(screen.getByTestId('entity-show-more')).toBeInTheDocument();
  });

  it('does NOT duplicate the fallback warning inside the card body', () => {
    const memoFb: Memo = {
      drivers: [{ name: 'Driver', description: 'desc' }],
    };
    const spot: WeakSpot = {
      ticker: 'CCJ',
      is_fallback_memo: true,
      is_momentum_trap: false,
      is_losing: false,
      current_pnl_pct: 0,
    };
    withAccordion(<MemoCard ticker="CCJ" memo={memoFb} weakSpot={spot} />);
    // Old Jinja UI rendered "memo writer fell back" inside the card body.
    // The redesign moves this to the summary row's WeakSpotIcons.
    expect(screen.queryByText(/memo writer fell back/i)).toBeNull();
  });
});
