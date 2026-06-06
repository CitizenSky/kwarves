import { describe, it, expect, vi } from 'vitest';

vi.mock('../src/state.js', () => ({
  colors: { green: '#2ca98c', yellow: '#e3b341', red: '#d35a5a', violet: '#9b59b6', gray: '#888888', spcPrep: '#d4a030' }
}));
vi.mock('../src/i18n.js', () => ({
  t: (key) => key,
  formatNumber: (n) => String(n),
  formatFloat: (n, d, f) => f ?? String(n)
}));

const { colorClass, isSpcPrepCandidate, isSpcArt, matrixColorClass, matrixText } = await import('../src/logic/colorFor.js');

function makeCandidate(overrides = {}) {
  return { color: 'yellow', tic: 123456789, evidenceScore: 75, isViolet: false, matrixClass: '', matrixStatus: '', status: '', ...overrides };
}

describe('colorClass', () => {
  it('returns green for green candidates', () => {
    expect(colorClass(makeCandidate({ color: 'green' }))).toBe('green');
  });
  it('returns violet when isViolet is true', () => {
    expect(colorClass(makeCandidate({ isViolet: true }))).toBe('violet');
  });
  it('returns spc-prep for SPC prep candidates', () => {
    const c = makeCandidate({ color: 'yellow', status: 'SPC_FOLLOWUP_READY' });
    expect(colorClass(c)).toBe('spc-prep');
  });
  it('returns color field as fallback', () => {
    expect(colorClass(makeCandidate({ color: 'red' }))).toBe('red');
  });
});

describe('isSpcPrepCandidate', () => {
  it('returns true when color=yellow and matrixText has SPC_FOLLOWUP_READY', () => {
    const c = makeCandidate({ color: 'yellow', matrixClass: 'SPC_FOLLOWUP_READY' });
    expect(isSpcPrepCandidate(c)).toBe(true);
  });
  it('returns false for green candidates regardless of text', () => {
    const c = makeCandidate({ color: 'green', matrixClass: 'SPC_FOLLOWUP_READY' });
    expect(isSpcPrepCandidate(c)).toBe(false);
  });
  it('returns false when matrixText lacks SPC_FOLLOWUP_READY', () => {
    const c = makeCandidate({ color: 'yellow', matrixClass: 'SPC_ART' });
    expect(isSpcPrepCandidate(c)).toBe(false);
  });
});

describe('isSpcArt', () => {
  it('returns true when matrixText includes SPC_ART', () => {
    expect(isSpcArt(makeCandidate({ matrixClass: 'SPC_ART' }))).toBe(true);
  });
  it('returns false otherwise', () => {
    expect(isSpcArt(makeCandidate({ matrixClass: 'SPC' }))).toBe(false);
  });
});

describe('matrixColorClass', () => {
  it('returns green when matrixColor is green', () => {
    expect(matrixColorClass(makeCandidate({ matrixColor: 'green' }))).toBe('green');
  });
  it('returns gray as fallback', () => {
    expect(matrixColorClass(makeCandidate({}))).toBe('gray');
  });
});
