import { describe, expect, it } from 'vitest';

import {
  alignmentColor,
  alignmentLabel,
  convictionColor,
  pnlColor,
  ratingColor,
  semanticClasses,
} from './derive';

// Filter-color contract. The matching Python rules used to live in
// tests/dashboard/test_filters.py; that file (and the Jinja filter module
// it tested) was deleted in dashboard-redesign Phase 6. These cases are
// now the canonical pin on the badge-color rules.
describe('convictionColor', () => {
  it.each([
    [5, 'good'],
    [4, 'good'],
    [3, 'warn'],
    [2, 'bad'],
    [1, 'bad'],
    [null, 'neutral'],
    ['banana', 'neutral'],
  ])('value %p → %s', (value, expected) => {
    expect(convictionColor(value as never)).toBe(expected);
  });
});

describe('alignmentColor', () => {
  it.each([
    ['aligned', 'good'],
    ['fully_diverged', 'bad'],
    ['partial_divergence', 'warn'],
    ['minor_divergence', 'warn'],
    ['unknown', 'neutral'],
    [null, 'neutral'],
  ])('value %p → %s', (value, expected) => {
    expect(alignmentColor(value)).toBe(expected);
  });
});

describe('alignmentLabel', () => {
  it('strips underscores', () => {
    expect(alignmentLabel('fully_diverged')).toBe('fully diverged');
  });
  it('passes already-spaced strings through', () => {
    expect(alignmentLabel('aligned')).toBe('aligned');
  });
  it('returns empty string for null', () => {
    expect(alignmentLabel(null)).toBe('');
  });
});

describe('ratingColor', () => {
  it.each([
    ['Buy', 'good'],
    ['Overweight', 'good'],
    ['Hold', 'warn'],
    ['Underweight', 'bad'],
    ['Sell', 'bad'],
    ['Hodl', 'neutral'],
    [null, 'neutral'],
  ])('rating %p → %s', (value, expected) => {
    expect(ratingColor(value)).toBe(expected);
  });
});

describe('pnlColor', () => {
  it.each([
    [1, 'good'],
    [0.001, 'good'],
    [0, 'neutral'],
    [-1, 'bad'],
    [null, 'neutral'],
    [NaN, 'neutral'],
  ])('value %p → %s', (value, expected) => {
    expect(pnlColor(value)).toBe(expected);
  });
});

describe('semanticClasses', () => {
  it('returns distinct token classes per color', () => {
    expect(semanticClasses('good').bg).toContain('good');
    expect(semanticClasses('warn').bg).toContain('warn');
    expect(semanticClasses('bad').bg).toContain('bad');
    expect(semanticClasses('neutral').bg).toContain('muted');
  });
});
