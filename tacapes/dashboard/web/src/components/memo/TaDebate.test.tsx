/**
 * TaDebate: debate-chronological section order, PM full decision auto-open,
 * empty / null tolerance.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { TaDebate, type TaOutputs } from './TaDebate';

describe('<TaDebate>', () => {
  it('omits sections that are missing or empty', () => {
    const ta: TaOutputs = {
      rating: 'Buy',
      full_decision_markdown: '## Decision\nBuy NRG.',
      market_report: '',
      news_report: null,
      sentiment_report: undefined,
      // fundamentals_report missing
      investment_plan: 'Enter at market open.',
    };
    render(<TaDebate ta={ta} />);
    expect(screen.getByText('PM full decision')).toBeInTheDocument();
    expect(screen.getByText('Research manager: investment plan')).toBeInTheDocument();
    expect(screen.queryByText('Analyst: market report')).toBeNull();
    expect(screen.queryByText('Analyst: news report')).toBeNull();
    expect(screen.queryByText('Analyst: fundamentals report')).toBeNull();
  });

  it('renders sections in debate-chronological order with PM full decision first', () => {
    const ta: TaOutputs = {
      market_report: 'm',
      news_report: 'n',
      sentiment_report: 's',
      fundamentals_report: 'f',
      investment_plan: 'ip',
      trader_investment_plan: 'tip',
      risk_debate_judge_decision: 'rdjd',
      full_decision_markdown: 'fd',
    };
    render(<TaDebate ta={ta} />);
    const triggers = screen.getAllByRole('button').map((b) => b.textContent);
    // The full decision is the first trigger; analysts come before the
    // research manager which comes before the trader, etc.
    expect(triggers).toEqual([
      'PM full decision',
      'Analyst: market report',
      'Analyst: news report',
      'Analyst: sentiment report',
      'Analyst: fundamentals report',
      'Research manager: investment plan',
      'Trader: transaction proposal',
      'Risk debate: judge decision',
    ]);
  });

  it('PM full decision is open by default', () => {
    const ta: TaOutputs = {
      full_decision_markdown: 'Buy.',
      market_report: 'm',
    };
    const { container } = render(<TaDebate ta={ta} />);
    const pmItem = container.querySelector(
      '[data-section="full_decision_markdown"]',
    );
    // Radix Accordion sets data-state on the item itself when open.
    expect(pmItem?.getAttribute('data-state')).toBe('open');
    const marketItem = container.querySelector('[data-section="market_report"]');
    expect(marketItem?.getAttribute('data-state')).toBe('closed');
  });

  it('renders an empty-state when ta is null', () => {
    render(<TaDebate ta={null} />);
    expect(screen.getByText(/no TradingAgents output recorded/i)).toBeInTheDocument();
  });
});
