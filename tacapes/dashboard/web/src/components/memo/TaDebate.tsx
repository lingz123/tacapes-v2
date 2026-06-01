/**
 * Renders one ticker's TradingAgents debate from `ta_outputs_json`.
 *
 * Sections are reordered debate-chronologically (market → news → sentiment →
 * fundamentals → investment_plan → trader_investment_plan →
 * risk_debate_judge_decision → full_decision_markdown). The PM full decision
 * is rendered first (auto-open) so the answer leads; analysts and judge
 * follow in pipeline order.
 *
 * Each section is a shadcn Accordion item so the user can keep most folded
 * and unfold only the panel they want to scrutinise.
 */
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { MdProse } from './MdProse';
import { RatingBadge } from '@/components/stat/RatingBadge';

interface TaOutputs {
  rating?: string | null;
  price_target?: number | null;
  time_horizon?: string | null;
  suggested_position_pct?: number | null;
  trade_date?: string | null;
  market_report?: string | null;
  news_report?: string | null;
  sentiment_report?: string | null;
  fundamentals_report?: string | null;
  investment_plan?: string | null;
  trader_investment_plan?: string | null;
  risk_debate_judge_decision?: string | null;
  full_decision_markdown?: string | null;
}

interface TaDebateProps {
  ta: TaOutputs | null | undefined;
}

// Debate-chronological order: each section feeds the next. The PM full
// decision sits at the top because it's the synthesised answer; everything
// else explains how the PM arrived there.
type Section = { key: keyof TaOutputs; label: string; defaultOpen?: boolean };
const SECTIONS: Section[] = [
  { key: 'full_decision_markdown', label: 'PM full decision', defaultOpen: true },
  { key: 'market_report', label: 'Analyst: market report' },
  { key: 'news_report', label: 'Analyst: news report' },
  { key: 'sentiment_report', label: 'Analyst: sentiment report' },
  { key: 'fundamentals_report', label: 'Analyst: fundamentals report' },
  { key: 'investment_plan', label: 'Research manager: investment plan' },
  { key: 'trader_investment_plan', label: 'Trader: transaction proposal' },
  { key: 'risk_debate_judge_decision', label: 'Risk debate: judge decision' },
];

export function TaDebate({ ta }: TaDebateProps) {
  if (!ta) {
    return (
      <p className="text-xs text-muted-foreground italic">
        no TradingAgents output recorded.
      </p>
    );
  }

  const present = SECTIONS.filter((s) => {
    const value = ta[s.key];
    return typeof value === 'string' && value.trim().length > 0;
  });

  if (present.length === 0) {
    return (
      <p className="text-xs text-muted-foreground italic">
        no detailed TA output recorded.
      </p>
    );
  }

  // Open the PM full decision by default, plus anything the section table
  // marked as defaultOpen.
  const defaultValue = present.filter((s) => s.defaultOpen).map((s) => s.key as string);

  return (
    <div className="space-y-3" data-testid="ta-debate">
      <TaHeader ta={ta} />
      <Accordion
        type="multiple"
        defaultValue={defaultValue}
        className="rounded-md border bg-card"
      >
        {present.map((section) => (
          <AccordionItem
            key={section.key as string}
            value={section.key as string}
            data-section={section.key as string}
          >
            <AccordionTrigger className="px-3 py-2 text-sm font-medium hover:no-underline">
              {section.label}
            </AccordionTrigger>
            <AccordionContent className="px-3 pb-3">
              <MdProse>{ta[section.key] as string}</MdProse>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}

function TaHeader({ ta }: { ta: TaOutputs }) {
  const chips: React.ReactNode[] = [];
  if (ta.price_target != null) {
    chips.push(
      <Badge key="pt" variant="outline" className="font-mono">
        target ${ta.price_target.toFixed(2)}
      </Badge>,
    );
  }
  if (ta.time_horizon) {
    chips.push(
      <Badge key="th" variant="outline" className="font-mono">
        horizon {ta.time_horizon}
      </Badge>,
    );
  }
  if (ta.suggested_position_pct != null) {
    chips.push(
      <Badge key="sp" variant="outline" className="font-mono">
        suggested {(ta.suggested_position_pct * 100).toFixed(1)}%
      </Badge>,
    );
  }
  if (ta.trade_date) {
    chips.push(
      <span key="td" className="text-xs text-muted-foreground">
        trade date {ta.trade_date}
      </span>,
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {ta.rating && <RatingBadge value={ta.rating} />}
      {chips}
    </div>
  );
}

export type { TaOutputs };
