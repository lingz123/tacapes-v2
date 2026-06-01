import { describe, expect, it } from 'vitest';

import { usd, pct, relativeDate } from './format';

describe('usd', () => {
  it('formats whole dollars by default', () => {
    expect(usd(20000)).toBe('$20,000');
  });
  it('formats cents when asked', () => {
    expect(usd(42.17, { cents: true })).toBe('$42.17');
  });
  it('emits em-dash for null', () => {
    expect(usd(null)).toBe('—');
  });
});

describe('pct', () => {
  it('signs positive values', () => {
    expect(pct(6.7)).toBe('+6.7%');
  });
  it('does not double-sign negatives', () => {
    expect(pct(-3.42)).toBe('-3.4%');
  });
  it('emits em-dash for null', () => {
    expect(pct(null)).toBe('—');
  });
});

describe('relativeDate', () => {
  it('returns "today" for now', () => {
    expect(relativeDate(new Date())).toBe('today');
  });
  it('returns "yesterday" for a day ago', () => {
    expect(relativeDate(new Date(Date.now() - 86_400_000))).toBe('yesterday');
  });
  it('emits em-dash for null', () => {
    expect(relativeDate(null)).toBe('—');
  });
});
