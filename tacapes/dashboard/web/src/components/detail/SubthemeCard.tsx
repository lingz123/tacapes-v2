/**
 * One card in the Zone B sub-theme grid.
 *
 * Shape per the redesign spec §5 + §13 (open question on backfilled missions):
 *   - name (always present)
 *   - description (falls back to "no description recorded" when the
 *     decomposition_json omitted hypothesis/description, common for
 *     pre-v2 backfilled missions)
 *   - candidate count + chosen ratio rendered as a dot row: filled dot
 *     per chosen, hollow dot per passed.
 *   - first 2 key findings as a tight bullet list. Empty findings → omit.
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { SubthemeSummary } from '@/types/api';

interface SubthemeCardProps {
  subtheme: SubthemeSummary;
  className?: string;
}

export function SubthemeCard({ subtheme, className }: SubthemeCardProps) {
  const { name, description, candidate_count, chosen_count, key_findings } = subtheme;
  const findings = key_findings.slice(0, 2);
  const passed = Math.max(0, candidate_count - chosen_count);

  return (
    <Card
      className={cn('shadow-sm', className)}
      data-testid="subtheme-card"
      data-subtheme-id={subtheme.id}
    >
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold tracking-tight leading-snug">
          {name}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pb-4">
        <p
          className={cn(
            'text-xs leading-relaxed',
            description ? 'text-foreground/80' : 'italic text-muted-foreground',
          )}
        >
          {description ?? 'no description recorded'}
        </p>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <DotRow chosen={chosen_count} passed={passed} />
          <span className="font-mono tabular-nums">
            {chosen_count}/{candidate_count} chosen
          </span>
        </div>

        {findings.length > 0 && (
          <ul className="space-y-1.5 text-xs text-foreground/85">
            {findings.map((line, i) => (
              <li key={i} className="flex gap-2 leading-snug">
                <span className="mt-1 inline-block size-1 rounded-full bg-muted-foreground/60 shrink-0" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function DotRow({ chosen, passed }: { chosen: number; passed: number }) {
  const total = chosen + passed;
  if (total === 0) {
    return <span className="text-[10px] italic">no candidates</span>;
  }
  // Cap at 12 dots so wide candidate sets don't blow out the card; show a
  // "+N" tail when truncated.
  const cap = 12;
  const visibleChosen = Math.min(chosen, cap);
  const remainingCap = cap - visibleChosen;
  const visiblePassed = Math.min(passed, remainingCap);
  const overflow = total - (visibleChosen + visiblePassed);
  return (
    <span className="inline-flex items-center gap-0.5" data-testid="subtheme-dots">
      {Array.from({ length: visibleChosen }).map((_, i) => (
        <span
          key={`c${i}`}
          className="inline-block size-2 rounded-full bg-foreground"
          data-dot="chosen"
        />
      ))}
      {Array.from({ length: visiblePassed }).map((_, i) => (
        <span
          key={`p${i}`}
          className="inline-block size-2 rounded-full border border-foreground/40"
          data-dot="passed"
        />
      ))}
      {overflow > 0 && (
        <span className="ml-1 text-[10px] font-mono">+{overflow}</span>
      )}
    </span>
  );
}
