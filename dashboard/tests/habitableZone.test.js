import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { isHabitableZoneCandidate, isHabitableZoneClass } from '../src/logic/habitableZone.js';

const dashboardRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

describe('habitable zone decision helper', () => {
  it('accepts only conservative and optimistic inner HZ classes', () => {
    expect(isHabitableZoneClass('KONSERVATIVE_HZ')).toBe(true);
    expect(isHabitableZoneClass('OPT_HZ_INNEN')).toBe(true);
    expect(isHabitableZoneClass(' konservative_hz ')).toBe(true);
  });

  it('excludes hot, unknown, empty, null, and missing HZ values', () => {
    expect(isHabitableZoneCandidate({ hz: 'ZU_HEISS' })).toBe(false);
    expect(isHabitableZoneCandidate({ hz: 'unknown' })).toBe(false);
    expect(isHabitableZoneCandidate({ hz: '' })).toBe(false);
    expect(isHabitableZoneCandidate({ hz: null })).toBe(false);
    expect(isHabitableZoneCandidate({})).toBe(false);
    expect(isHabitableZoneCandidate(null)).toBe(false);
  });

  it('keeps candidates-summary.json HZ candidates limited to valid classes', () => {
    const payload = JSON.parse(fs.readFileSync(path.join(dashboardRoot, 'candidates-summary.json'), 'utf8'));
    const hzCandidates = payload.candidates.filter(isHabitableZoneCandidate);

    expect(hzCandidates).toHaveLength(78);
    expect(new Set(hzCandidates.map((candidate) => candidate.hz))).toEqual(new Set(['KONSERVATIVE_HZ', 'OPT_HZ_INNEN']));
    expect(payload.candidates.filter((candidate) => candidate.hz === 'ZU_HEISS' && isHabitableZoneCandidate(candidate))).toHaveLength(0);
  });

  it('keeps lazy candidate-details HZ candidates limited to valid classes', () => {
    const detailsDir = path.join(dashboardRoot, 'candidate-details');
    const candidates = fs.readdirSync(detailsDir)
      .filter((fileName) => fileName.endsWith('.json'))
      .map((fileName) => JSON.parse(fs.readFileSync(path.join(detailsDir, fileName), 'utf8')));
    const hzCandidates = candidates.filter(isHabitableZoneCandidate);

    expect(candidates).toHaveLength(2049);
    expect(hzCandidates).toHaveLength(78);
    expect(new Set(hzCandidates.map((candidate) => candidate.hz))).toEqual(new Set(['KONSERVATIVE_HZ', 'OPT_HZ_INNEN']));
    expect(candidates.filter((candidate) => candidate.hz === 'ZU_HEISS' && isHabitableZoneCandidate(candidate))).toHaveLength(0);
  });

  it('renders the matrix from the active filtered candidate set', () => {
    const source = fs.readFileSync(path.join(dashboardRoot, 'src/components/candidateList.js'), 'utf8');

    expect(source).toContain('let rows = filteredCandidates();');
    expect(source).not.toContain('let rows = publicMatrixCandidates();');
  });
});
