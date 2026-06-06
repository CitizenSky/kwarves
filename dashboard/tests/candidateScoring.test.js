import { describe, it, expect, vi } from 'vitest';

vi.mock('../src/state.js', () => ({ state: { selected: null, colorFilter: 'all' }, colors: {} }));
vi.mock('../src/i18n.js', () => ({ t: (key) => key, formatNumber: (n) => String(n), formatFloat: (n) => String(n), formatMaybe: (v, d) => v ?? d }));
vi.mock('../src/dataLoader.js', () => ({ data: { candidates: [] } }));
vi.mock('../src/logic/colorFor.js', () => {
  const mt = (c) => [c.status, c.matrixStatus, c.matrixClass, c.matrixScoreBand, c.decisionReason, c.nextStep].filter(Boolean).join(' ').toUpperCase();
  return {
    matrixText: mt,
    localizedBaseColorLabel: () => 'yellow',
    isSpcStrong: (c) => mt(c).includes('SPC_STRONG'),
    isSpcPrepCandidate: (c) => c.color === 'yellow' && mt(c).includes('SPC_FOLLOWUP_READY'),
    isSpcArt: (c) => mt(c).includes('SPC_ART'),
    isSpc: (c) => mt(c).includes('SPC_STRONG') || mt(c).includes('RV_NEEDED') || mt(c).includes('SPC_FOLLOWUP_READY') || c.color === 'green',
    isRvNeeded: (c) => mt(c).includes('RV_NEEDED')
  };
});
vi.mock('../src/logic/candidateLabel.js', () => ({ candidateLabel: (c) => c.matrixClass || 'UNKNOWN' }));

const { matrixStatusBucket, hzPriority, followupRank, countWhere, expectedTransits, visibleMatrixTransits, coveragePercent, numericBucket } = await import('../src/logic/candidateScoring.js');

function makeCandidate(overrides = {}) {
  return { tic: 123456789, color: 'yellow', evidenceScore: 75, distance: 100, period: 10, snr: 12, isViolet: false, hz: 'KONSERVATIVE_HZ', matrixClass: '', matrixStatus: '', status: '', matrixTransits: 5, transits: 5, matrixVisibleTransits: 3, visibleTransits: 3, followupStrength: '', ...overrides };
}

describe('matrixStatusBucket', () => {
  it('returns EB_RISK for eclipsing binary risk', () => {
    expect(matrixStatusBucket(makeCandidate({ matrixClass: 'EB_RISK' }))).toBe('EB_RISK');
  });
  it('returns IGNORE when matrixStatus is IGNORE', () => {
    expect(matrixStatusBucket(makeCandidate({ matrixStatus: 'IGNORE', matrixClass: 'SOMETHING' }))).toBe('IGNORE');
  });
  it('returns REJECTED when text includes REJECT', () => {
    expect(matrixStatusBucket(makeCandidate({ matrixClass: 'REJECT' }))).toBe('REJECTED');
  });
  it('returns IGNORE as default fallback', () => {
    expect(matrixStatusBucket(makeCandidate({ color: 'yellow', matrixClass: '', matrixStatus: '', status: 'UNKNOWN' }))).toBe('IGNORE');
  });
});

describe('hzPriority', () => {
  it('returns 0 for violet candidates', () => {
    expect(hzPriority(makeCandidate({ isViolet: true }))).toBe(0);
  });
  it('returns 1 for non-violet candidates with HZ', () => {
    expect(hzPriority(makeCandidate({ isViolet: false, hz: 'KONSERVATIVE_HZ' }))).toBe(1);
  });
  it('returns 2 for ZU_HEISS', () => {
    expect(hzPriority(makeCandidate({ isViolet: false, hz: 'ZU_HEISS' }))).toBe(2);
  });
});

describe('followupRank', () => {
  it('returns 0 for STRONG followup', () => {
    expect(followupRank(makeCandidate({ followupStrength: 'STRONG' }))).toBe(0);
  });
  it('returns 1 for green candidates', () => {
    expect(followupRank(makeCandidate({ color: 'green' }))).toBe(1);
  });
  it('returns 2 for MEDIUM followup', () => {
    expect(followupRank(makeCandidate({ followupStrength: 'MEDIUM' }))).toBe(2);
  });
  it('returns 3 as default', () => {
    expect(followupRank(makeCandidate({ color: 'red' }))).toBe(3);
  });
});

describe('countWhere', () => {
  it('counts items matching predicate', () => {
    expect(countWhere([1, 2, 3, 4, 5], (n) => n > 3)).toBe(2);
  });
  it('returns 0 for empty array', () => {
    expect(countWhere([], () => true)).toBe(0);
  });
});

describe('expectedTransits', () => {
  it('returns matrixTransits when available', () => {
    expect(expectedTransits(makeCandidate({ matrixTransits: 7 }))).toBe(7);
  });
  it('falls back to transits', () => {
    expect(expectedTransits(makeCandidate({ matrixTransits: undefined, transits: 4 }))).toBe(4);
  });
  it('returns 0 when neither is set', () => {
    expect(expectedTransits(makeCandidate({ matrixTransits: undefined, transits: undefined }))).toBe(0);
  });
});

describe('coveragePercent', () => {
  it('calculates percentage from visible/expected ratio', () => {
    expect(coveragePercent(makeCandidate({ matrixVisibleTransits: 3, matrixTransits: 6 }))).toBe(50);
  });
  it('returns 0 when no expected transits', () => {
    expect(coveragePercent(makeCandidate({ matrixTransits: 0 }))).toBe(0);
  });
});
