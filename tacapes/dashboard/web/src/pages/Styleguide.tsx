/**
 * Dev-only styleguide route at `/styleguide`. Renders every custom component
 * against sample inputs covering all semantic colors plus the null/unknown
 * edge cases. Lets us eyeball drift in one place without spinning up a real
 * mission.
 *
 * REMOVE before Sprint 1 close (Phase 7). Tracked in
 * docs/superpowers/plans/2026-05-31-dashboard-redesign.md §4.
 */
import { AppShell } from '@/components/shell/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { ConvictionBadge } from '@/components/stat/ConvictionBadge';
import { AlignmentBadge } from '@/components/stat/AlignmentBadge';
import { RatingBadge } from '@/components/stat/RatingBadge';
import { PnlPill } from '@/components/stat/PnlPill';
import { StatStrip } from '@/components/stat/StatStrip';
import { usd, pct, relativeDate } from '@/lib/format';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-4">
      <span className="w-40 text-xs text-muted-foreground font-mono">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function StyleguidePage() {
  return (
    <AppShell
      onNewMission={() => console.log('new mission clicked')}
      onRefreshPrices={() => console.log('refresh prices clicked')}
    >
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Styleguide</h1>
        <p className="text-sm text-muted-foreground">
          Every custom component against sample data. Dev only. Removed before Sprint 1 close.
        </p>
      </div>

      <Section title="ConvictionBadge">
        <Row label="1..5 + null">
          <ConvictionBadge value={5} />
          <ConvictionBadge value={4} />
          <ConvictionBadge value={3} />
          <ConvictionBadge value={2} />
          <ConvictionBadge value={1} />
          <ConvictionBadge value={null} />
        </Row>
      </Section>

      <Section title="AlignmentBadge">
        <Row label="alignment values">
          <AlignmentBadge value="aligned" />
          <AlignmentBadge value="partial_divergence" />
          <AlignmentBadge value="minor_divergence" />
          <AlignmentBadge value="fully_diverged" />
          <AlignmentBadge value={null} />
        </Row>
      </Section>

      <Section title="RatingBadge">
        <Row label="PortfolioRating">
          <RatingBadge value="Buy" />
          <RatingBadge value="Overweight" />
          <RatingBadge value="Hold" />
          <RatingBadge value="Underweight" />
          <RatingBadge value="Sell" />
          <RatingBadge value={null} />
        </Row>
      </Section>

      <Section title="PnlPill">
        <Row label="signs + null">
          <PnlPill value={14.2} />
          <PnlPill value={0.1} />
          <PnlPill value={0} />
          <PnlPill value={-3.4} />
          <PnlPill value={-22.7} />
          <PnlPill value={null} />
        </Row>
        <Row label="no glyph">
          <PnlPill value={14.2} noGlyph />
          <PnlPill value={-3.4} noGlyph />
        </Row>
      </Section>

      <Section title="StatStrip">
        <p className="text-xs text-muted-foreground">Full 6-tile strip:</p>
        <StatStrip
          tiles={[
            { label: 'Invested', value: usd(20000) },
            { label: 'Current', value: usd(21340) },
            {
              label: 'P&L',
              value: pct(6.7),
              accent: 'good',
              delta: <PnlPill value={1340} noGlyph />,
            },
            { label: 'Cash', value: '0%' },
            { label: 'Positions', value: '4 of 4' },
            { label: 'Unpriced', value: 0 },
          ]}
        />
        <Separator />
        <p className="text-xs text-muted-foreground">Degraded (some tiles null):</p>
        <StatStrip
          tiles={[
            { label: 'Invested', value: usd(10000) },
            { label: 'Current', value: null },
            { label: 'P&L', value: null, accent: 'neutral' },
            { label: 'Positions', value: '3 of 5' },
          ]}
        />
      </Section>

      <Section title="Formatters">
        <Row label="usd">
          <code className="text-sm">{usd(20000)}</code>
          <code className="text-sm">{usd(42.17, { cents: true })}</code>
          <code className="text-sm">{usd(null)}</code>
        </Row>
        <Row label="pct">
          <code className="text-sm">{pct(6.7)}</code>
          <code className="text-sm">{pct(-3.42, 2)}</code>
          <code className="text-sm">{pct(null)}</code>
        </Row>
        <Row label="relativeDate">
          <code className="text-sm">{relativeDate(new Date())}</code>
          <code className="text-sm">
            {relativeDate(new Date(Date.now() - 2 * 86_400_000))}
          </code>
          <code className="text-sm">{relativeDate('2026-01-01')}</code>
        </Row>
      </Section>
    </AppShell>
  );
}
