/**
 * Semantic-color derivations for badges and pills.
 *
 * Direct ports of what was once `tacapes/dashboard/filters.py` (Jinja).
 * That module was deleted in the dashboard-redesign Phase 6 cutover; this
 * file is now the single source of truth for the badge-color rules.
 *
 * Output is one of four discriminants: `good` (green), `warn` (amber),
 * `bad` (red), `neutral` (no accent). Components map these to color
 * classes via the tokens in styles/tokens.css.
 */

export type SemanticColor = 'good' | 'warn' | 'bad' | 'neutral';

/**
 * Conviction is 1-5 from the memo writer:
 *   4-5 → good, 3 → warn, 1-2 → bad, anything unparseable → neutral.
 */
export function convictionColor(conv: number | string | null | undefined): SemanticColor {
  // Mirror the Python filter: null/undefined/empty/unparseable → neutral.
  // JS quirk: Number(null) === 0, so we have to guard before coercing.
  if (conv == null || conv === '') return 'neutral';
  const n = typeof conv === 'number' ? conv : Number(conv);
  if (!Number.isFinite(n)) return 'neutral';
  if (n >= 4) return 'good';
  if (n === 3) return 'warn';
  return 'bad';
}

/**
 * Thesis alignment from the memo writer:
 *   aligned → good
 *   fully_diverged → bad
 *   *_divergence (partial/minor/etc.) → warn
 *   anything else → neutral.
 */
export function alignmentColor(align: string | null | undefined): SemanticColor {
  if (align === 'aligned') return 'good';
  if (align === 'fully_diverged') return 'bad';
  if (typeof align === 'string' && align.includes('divergence')) return 'warn';
  return 'neutral';
}

/** "fully_diverged" reads better as "fully diverged" in the UI. */
export function alignmentLabel(align: string | null | undefined): string {
  if (typeof align !== 'string') return '';
  return align.replace(/_/g, ' ');
}

/**
 * PortfolioRating mapped to a semantic color:
 *   Buy / Overweight → good
 *   Hold → warn
 *   Underweight / Sell → bad
 */
export function ratingColor(rating: string | null | undefined): SemanticColor {
  if (rating === 'Buy' || rating === 'Overweight') return 'good';
  if (rating === 'Hold') return 'warn';
  if (rating === 'Underweight' || rating === 'Sell') return 'bad';
  return 'neutral';
}

/**
 * P&L percent → good (positive), bad (negative), neutral (zero or missing).
 * Not in the Jinja filter set (the old UI just colored signs by hand); kept
 * here so PnlPill stays consistent with the rest of the badge palette.
 */
export function pnlColor(value: number | null | undefined): SemanticColor {
  if (value == null || !Number.isFinite(value)) return 'neutral';
  if (value > 0) return 'good';
  if (value < 0) return 'bad';
  return 'neutral';
}

/**
 * Class-name fragments per semantic color. Used by the badge wrappers so the
 * surface uses the `--{color}-bg` token and text uses the `--{color}` token.
 * Returns Tailwind utilities; consumers compose with their own classes.
 */
export function semanticClasses(color: SemanticColor): {
  bg: string;
  text: string;
  border: string;
} {
  switch (color) {
    case 'good':
      return { bg: 'bg-good-bg', text: 'text-good', border: 'border-good/20' };
    case 'warn':
      return { bg: 'bg-warn-bg', text: 'text-warn', border: 'border-warn/20' };
    case 'bad':
      return { bg: 'bg-bad-bg', text: 'text-bad', border: 'border-bad/20' };
    case 'neutral':
    default:
      return { bg: 'bg-muted', text: 'text-muted-foreground', border: 'border-border' };
  }
}
