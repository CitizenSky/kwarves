import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { candidateMatchesColorFilter } from '../src/logic/candidateFilters.js';
import { isHabitableZoneCandidate } from '../src/logic/habitableZone.js';
import { isSpcPrepCandidate } from '../src/logic/colorFor.js';

const dashboardRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function makeCandidate(overrides = {}) {
  return {
    tic: 1,
    color: 'yellow',
    hz: 'ZU_HEISS',
    matrixClass: '',
    matrixStatus: '',
    status: '',
    displayLabels: [],
    ...overrides,
  };
}

describe('candidate color filters', () => {
  it('keeps green, red, yellow, SPC prep, and HZ filters mutually precise', () => {
    const green = makeCandidate({ tic: 1, color: 'green' });
    const yellow = makeCandidate({ tic: 2, color: 'yellow', matrixClass: 'SPC_ART' });
    const spcPrep = makeCandidate({ tic: 3, color: 'yellow', matrixClass: 'SPC_FOLLOWUP_READY' });
    const red = makeCandidate({ tic: 4, color: 'red' });
    const hz = makeCandidate({ tic: 5, color: 'yellow', hz: 'KONSERVATIVE_HZ' });
    const hotVioletMarker = makeCandidate({ tic: 6, color: 'yellow', hz: 'ZU_HEISS', isViolet: true });
    const vvtReview = makeCandidate({ tic: 7, color: 'gray', vvtStatus: 'NEEDS_REVIEW' });
    const vvtBlocked = makeCandidate({ tic: 8, color: 'yellow', vvtStatus: 'BLOCKED', matrixClass: 'SPC_ART' });
    const candidates = [green, yellow, spcPrep, red, hz, hotVioletMarker, vvtReview, vvtBlocked];

    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'all')).map((c) => c.tic)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'green')).map((c) => c.tic)).toEqual([1]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'yellow')).map((c) => c.tic)).toEqual([2, 5, 6, 8]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'spc-prep')).map((c) => c.tic)).toEqual([3]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'vvt')).map((c) => c.tic)).toEqual([1, 3, 7]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'red')).map((c) => c.tic)).toEqual([4]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'violet')).map((c) => c.tic)).toEqual([5]);
    expect(candidateMatchesColorFilter(hotVioletMarker, 'violet')).toBe(false);
  });

  it('matches the real summary data buckets without leaking hot stars into HZ', () => {
    const payload = JSON.parse(fs.readFileSync(path.join(dashboardRoot, 'candidates-summary.json'), 'utf8'));
    const candidates = payload.candidates;
    const filter = (name) => candidates.filter((candidate) => candidateMatchesColorFilter(candidate, name));

    expect(filter('all')).toHaveLength(candidates.length);
    expect(filter('green').every((candidate) => candidate.color === 'green')).toBe(true);
    expect(filter('red').every((candidate) => candidate.color === 'red')).toBe(true);
    expect(filter('spc-prep').every(isSpcPrepCandidate)).toBe(true);
    expect(filter('yellow').every((candidate) => candidate.color === 'yellow' && !isSpcPrepCandidate(candidate))).toBe(true);
    expect(filter('vvt')).toHaveLength(402);
    expect(filter('vvt').every((candidate) => !/FALSE_POSITIVE|RED_FP|EB_RISK|REJECTED|IGNORE/.test([
      candidate.status,
      candidate.matrixStatus,
      candidate.matrixClass,
      candidate.matrixScoreBand,
      candidate.decisionReason,
      candidate.nextStep,
    ].filter(Boolean).join(' ').toUpperCase()))).toBe(true);
    expect(filter('violet')).toHaveLength(78);
    expect(filter('violet').every(isHabitableZoneCandidate)).toBe(true);
    expect(filter('violet').some((candidate) => candidate.hz === 'ZU_HEISS')).toBe(false);
  });

  it('keeps one canonical dashboard color filter control per filter value', () => {
    const template = fs.readFileSync(path.join(dashboardRoot, 'index.src.html'), 'utf8');
    const matches = [...template.matchAll(/data-color-filter="([^"]+)"/g)].map((match) => match[1]);

    expect(matches).toEqual(['all', 'vvt', 'green', 'yellow', 'spc-prep', 'red', 'violet']);
  });
});
