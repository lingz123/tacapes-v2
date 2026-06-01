/**
 * Formatting helpers for prices, percentages, and dates.
 *
 * Kept dependency-free (no date-fns, no Intl polyfill) since we only need
 * USD and en-US locale for a local dashboard. If we ever ship i18n, swap
 * these for locale-aware versions in one file.
 */

const USD_FORMAT = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const USD_DECIMAL_FORMAT = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const DATE_FORMAT = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
});

/**
 * Whole-dollar by default ($20,000). Pass `cents: true` for two-decimal
 * precision used in entry / current prices ($42.17).
 */
export function usd(value: number | null | undefined, opts: { cents?: boolean } = {}): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return opts.cents ? USD_DECIMAL_FORMAT.format(value) : USD_FORMAT.format(value);
}

/**
 * Percent display. Backend ships percents as numbers (e.g. 6.73), not ratios.
 * Default precision is 1 decimal place; pass `digits` to override.
 * Always includes the sign for non-zero values.
 */
export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

/**
 * Short relative date for table rows: "today", "yesterday", "3 days ago",
 * or the absolute date for anything older than a week. Tooltips can show
 * the full ISO string separately.
 */
export function relativeDate(iso: string | Date | null | undefined): string {
  if (!iso) return '—';
  const date = typeof iso === 'string' ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return '—';
  const now = Date.now();
  const diffMs = now - date.getTime();
  const day = 86_400_000;
  const days = Math.floor(diffMs / day);
  if (days < 0) return DATE_FORMAT.format(date);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  return DATE_FORMAT.format(date);
}
