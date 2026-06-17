import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  candidateMatchesColorFilter,
  hasRealVettingData,
  isTtvMultiPlanetReviewCandidate,
  isVvtBroadReviewCandidate,
  isVvtShortlistCandidate,
} from '../src/logic/candidateFilters.js';
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
    lightcurveImg: 'lightcurves/TIC_1.png',
    hasRealVettingData: true,
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
    const vvtReview = makeCandidate({ tic: 7, color: 'gray', vvtStatus: 'NEEDS_REVIEW', vvtScore: 72 });
    const vvtBlocked = makeCandidate({ tic: 8, color: 'yellow', vvtStatus: 'BLOCKED', matrixClass: 'SPC_ART' });
    const ttvReview = makeCandidate({ tic: 9, color: 'yellow', ttvStatus: 'POSSIBLE_TTV' });
    const candidates = [green, yellow, spcPrep, red, hz, hotVioletMarker, vvtReview, vvtBlocked, ttvReview];

    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'all')).map((c) => c.tic)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'green')).map((c) => c.tic)).toEqual([1]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'yellow')).map((c) => c.tic)).toEqual([2, 5, 6, 8, 9]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'spc-prep')).map((c) => c.tic)).toEqual([3]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'vvt')).map((c) => c.tic)).toEqual([7]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'ttv')).map((c) => c.tic)).toEqual([9]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'red')).map((c) => c.tic)).toEqual([4]);
    expect(candidates.filter((candidate) => candidateMatchesColorFilter(candidate, 'violet')).map((c) => c.tic)).toEqual([5]);
    expect(candidateMatchesColorFilter(hotVioletMarker, 'violet')).toBe(false);
  });

  it('uses strict VVT shortlist rules for the matrix filter', () => {
    const exofopReady = makeCandidate({ tic: 10, vvtStatus: 'EXOFOP_READY', vvtScore: 20 });
    const reviewHighScore = makeCandidate({ tic: 11, vvtStatus: 'NEEDS_REVIEW', vvtScore: 70 });
    const reviewLowScore = makeCandidate({ tic: 12, vvtStatus: 'NEEDS_REVIEW', vvtScore: 69 });
    const spcStrongHighEvidence = makeCandidate({ tic: 13, vvtStatus: 'WAIT_FOR_DATA', vvtScore: 10, matrixClass: 'SPC_STRONG', evidenceScore: 80 });
    const spcStrongLowEvidence = makeCandidate({ tic: 14, vvtStatus: 'WAIT_FOR_DATA', vvtScore: 10, matrixClass: 'SPC_STRONG', evidenceScore: 79 });
    const hardBlocked = makeCandidate({ tic: 15, vvtStatus: 'NEEDS_REVIEW', vvtScore: 90, vvtBlockingIssues: ['Known false-positive or eclipsing-binary risk'] });
    const withoutLightcurve = makeCandidate({ tic: 16, vvtStatus: 'NEEDS_REVIEW', vvtScore: 90, lightcurveImg: '' });
    const ttvReviewOnly = makeCandidate({
      tic: 17,
      vvtStatus: 'NEEDS_REVIEW',
      vvtScore: 72,
      ttvStatus: 'TIMING_OR_DEPTH_SCATTER_RISK',
      vvtBlockingIssues: [],
      vvtReviewNotes: ['TIMING_OR_DEPTH_SCATTER_RISK: manual timing review; not a hard blocker by itself'],
    });

    expect(isVvtShortlistCandidate(exofopReady)).toBe(true);
    expect(isVvtShortlistCandidate(reviewHighScore)).toBe(true);
    expect(isVvtShortlistCandidate(reviewLowScore)).toBe(false);
    expect(isVvtShortlistCandidate(spcStrongHighEvidence)).toBe(true);
    expect(isVvtShortlistCandidate(spcStrongLowEvidence)).toBe(false);
    expect(isVvtShortlistCandidate(hardBlocked)).toBe(false);
    expect(isVvtShortlistCandidate(withoutLightcurve)).toBe(false);
    expect(isVvtShortlistCandidate(ttvReviewOnly)).toBe(true);
  });

  it('uses TTV / multi-planet review as a science-interest filter, not an FP filter', () => {
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ ttvStatus: 'POSSIBLE_TTV' }))).toBe(true);
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ ttvStatus: 'STRONG_TTV' }))).toBe(true);
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ ttvStatus: 'IRREGULAR_TTV' }))).toBe(true);
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ candidateFlags: ['MULTI_SIGNAL_CANDIDATE'] }))).toBe(true);
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ displayLabels: ['MULTI_PLANET_CANDIDATE'] }))).toBe(true);
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ ttvStatus: 'NO_STRONG_TTV_FLAG' }))).toBe(false);
    expect(isTtvMultiPlanetReviewCandidate(makeCandidate({ ttvStatus: 'TIMING_OR_DEPTH_SCATTER_RISK' }))).toBe(false);
    expect(candidateMatchesColorFilter(makeCandidate({ ttvStatus: 'STRONG_TTV', matrixClass: 'FALSE_POSITIVE' }), 'ttv')).toBe(true);
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
    expect(candidates.filter(isVvtBroadReviewCandidate)).toHaveLength(402);
    expect(filter('vvt')).toHaveLength(13);
    expect(filter('vvt').length).toBeLessThan(candidates.filter(isVvtBroadReviewCandidate).length);
    expect(filter('vvt').every((candidate) => !/FALSE_POSITIVE|RED_FP|EB_RISK|REJECTED|IGNORE/.test([
      candidate.status,
      candidate.matrixStatus,
      candidate.matrixClass,
      candidate.matrixScoreBand,
      candidate.decisionReason,
      candidate.nextStep,
    ].filter(Boolean).join(' ').toUpperCase()))).toBe(true);
    expect(filter('vvt').every((candidate) => candidate.hasRealLightcurve === true && hasRealVettingData(candidate))).toBe(true);
    expect(filter('vvt').every((candidate) => (candidate.vvtBlockingIssues || []).join(' ').match(/TTV|TIMING|SCATTER/i) || (candidate.vvtBlockingIssues || []).length === 0)).toBe(true);
    expect(filter('ttv').every(isTtvMultiPlanetReviewCandidate)).toBe(true);
    expect(filter('violet')).toHaveLength(78);
    expect(filter('violet').every(isHabitableZoneCandidate)).toBe(true);
    expect(filter('violet').some((candidate) => candidate.hz === 'ZU_HEISS')).toBe(false);
  });

  it('backs every real VVT shortlist candidate with detail-level lightcurve and vetting data', () => {
    const payload = JSON.parse(fs.readFileSync(path.join(dashboardRoot, 'candidates-summary.json'), 'utf8'));
    const shortlist = payload.candidates.filter(isVvtShortlistCandidate);

    expect(shortlist).toHaveLength(13);
    for (const summaryCandidate of shortlist) {
      const detail = JSON.parse(fs.readFileSync(path.join(dashboardRoot, `candidate-details/TIC_${summaryCandidate.tic}.json`), 'utf8'));
      const stats = detail.individualTransitStatistics || {};
      const stage2 = detail.spcArtStage2 || {};
      const hasLevel5 = stats.source === 'LEVEL5_SINGLE_TRANSITS' && stats.csvAvailable !== false && Number(stats.individualTransitCount || 0) > 0;
      const hasStage2 = Boolean(
        stage2.source &&
        !/MISSING|SYNTHETIC|FALLBACK|RUNTIME_FALLBACK|LIMITED_EXPORT/.test(String(stage2.source).toUpperCase()) &&
        stage2.fallbackUsed !== true &&
        stage2.stage2Completed !== false &&
        String(stage2.computationStatus || '').toUpperCase() !== 'NOT_COMPUTED'
      );

      expect(summaryCandidate.hasRealLightcurve).toBe(true);
      expect(summaryCandidate.hasRealVettingData).toBe(true);
      expect(detail.lightcurveImg).toBe(`lightcurves/TIC_${summaryCandidate.tic}.png`);
      expect(detail.hasRealVettingData).toBe(true);
      expect(hasLevel5 || hasStage2).toBe(true);
    }
  });

  it('keeps one canonical dashboard color filter control per filter value', () => {
    const template = fs.readFileSync(path.join(dashboardRoot, 'index.src.html'), 'utf8');
    const matches = [...template.matchAll(/data-color-filter="([^"]+)"/g)].map((match) => match[1]);

    expect(matches).toEqual(['all', 'vvt', 'ttv', 'green', 'yellow', 'spc-prep', 'red', 'violet']);
  });
});
