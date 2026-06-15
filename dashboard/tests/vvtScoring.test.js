import { describe, expect, it } from 'vitest';
import { evaluateVvt } from '../src/logic/vvtScoring.js';

function makeCandidate(overrides = {}) {
  return {
    tic: 75878355,
    color: 'green',
    evidenceScore: 92,
    multiMethodScore: 88,
    multiMethodCleanForExofop: true,
    transitEvidenceStatus: 'SUPPORTS',
    ttvStatus: 'NO_STRONG_TTV_FLAG',
    blendStatus: 'NO_LOCAL_BLEND_FLAG',
    knownObjectStatus: 'NO_KNOWN_MATCH',
    variabilityStatus: 'CLEAN',
    observedSectorCount: 4,
    matrixVisibleTransits: 3,
    status: 'SPC',
    matrixClass: 'SPC_STRONG',
    ...overrides
  };
}

describe('evaluateVvt', () => {
  it('marks clean high-score candidates as EXOFOP_READY', () => {
    const result = evaluateVvt(makeCandidate());

    expect(result.vvtStatus).toBe('EXOFOP_READY');
    expect(result.vvtScore).toBeGreaterThanOrEqual(85);
    expect(result.vvtBlockingIssues).toEqual([]);
  });

  it('returns WAIT_FOR_DATA when coverage is insufficient', () => {
    const result = evaluateVvt(makeCandidate({
      observedSectorCount: 1,
      matrixVisibleTransits: 1
    }));

    expect(result.vvtStatus).toBe('WAIT_FOR_DATA');
    expect(result.vvtBlockingIssues.join(' ')).toContain('WAIT_FOR_DATA');
  });

  it('blocks known false positives or eclipsing-binary risk', () => {
    const result = evaluateVvt(makeCandidate({
      knownObjectStatus: 'KNOWN_FP_OR_EB',
      matrixClass: 'EB_RISK'
    }));

    expect(result.vvtStatus).toBe('BLOCKED');
    expect(result.vvtBlockingIssues).toContain('Known false-positive or eclipsing-binary risk');
  });

  it('does not treat strong or irregular TTV as a hard blocker by itself', () => {
    const result = evaluateVvt(makeCandidate({
      ttvStatus: 'TIMING_OR_DEPTH_SCATTER_RISK',
      multiMethodScore: 76
    }));

    expect(result.vvtStatus).not.toBe('BLOCKED');
    expect(result.vvtBlockingIssues).toEqual([]);
    expect(result.vvtReviewNotes.join(' ')).toContain('not a hard blocker');
  });
});

