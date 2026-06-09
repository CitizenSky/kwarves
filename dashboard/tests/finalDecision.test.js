import { describe, it, expect } from 'vitest';
import {
  computeFinalDecision,
  computeSignalQuality,
  computeDataQuality,
  checkTessData,
  checkSignalDetection,
  checkFoldedLightCurve,
  checkSectorCoverage,
  checkTransitCount,
  checkOddEven,
  checkSecondaryEclipse,
  checkSapPdcsap,
  checkActivityRotation,
  evaluateSpcArtStage2,
  classifyFoldedLightCurve,
  runAllChecks,
  MIN_SECTORS_FOR_DATA,
  MIN_TRANSITS_FOR_DATA,
  STRONG_SCORE,
  MEDIUM_SCORE,
  HIGH_SECTORS,
  HIGH_TRANSITS,
  SIGNAL_MIN_SCORE
} from '../src/logic/finalDecision.js';

function makeCandidate(overrides = {}) {
  return {
    tic: 123456789,
    color: "yellow",
    evidenceScore: 55,
    status: "SPC-C",
    matrixStatus: "NEEDS_MORE_DATA",
    matrixClass: "SPC_C",
    transitShape: "U_SHAPE",
    sapPdcsapMatch: "OK",
    oddEvenResult: "OK",
    secondaryEclipse: "NO",
    rotationRisk: "LOW",
    observedSectorCount: 5,
    matrixVisibleTransits: 4,
    visibleTransits: 4,
    isViolet: false,
    hz: "KONSERVATIVE_HZ",
    ...overrides
  };
}

describe('checkTessData', () => {
  it('passes when sectors are available', () => {
    expect(checkTessData(makeCandidate({ observedSectorCount: 3 })).status).toBe("passed");
  });
  it('fails when no sectors', () => {
    expect(checkTessData(makeCandidate({ observedSectorCount: 0 })).status).toBe("failed");
  });
  it('fails when sectors is null', () => {
    expect(checkTessData(makeCandidate({ observedSectorCount: null })).status).toBe("failed");
  });
});

describe('checkSignalDetection', () => {
  it('passes with evidenceScore >= SIGNAL_MIN_SCORE', () => {
    expect(checkSignalDetection(makeCandidate({ evidenceScore: SIGNAL_MIN_SCORE })).status).toBe("passed");
  });
  it('fails with evidenceScore < SIGNAL_MIN_SCORE', () => {
    expect(checkSignalDetection(makeCandidate({ evidenceScore: SIGNAL_MIN_SCORE - 1 })).status).toBe("failed");
  });
  it('fails with null evidenceScore', () => {
    expect(checkSignalDetection(makeCandidate({ evidenceScore: null })).status).toBe("failed");
  });
});

describe('checkFoldedLightCurve', () => {
  it('passes with U_SHAPE', () => {
    expect(checkFoldedLightCurve(makeCandidate({ transitShape: "U_SHAPE" })).status).toBe("passed");
  });
  it('fails with V_SHAPE', () => {
    expect(checkFoldedLightCurve(makeCandidate({ transitShape: "V_SHAPE" })).status).toBe("failed");
  });
  it('warns with UNKNOWN', () => {
    expect(checkFoldedLightCurve(makeCandidate({ transitShape: "UNKNOWN" })).status).toBe("warning");
  });
  it('warns with ASYMMETRIC', () => {
    expect(checkFoldedLightCurve(makeCandidate({ transitShape: "ASYMMETRIC" })).status).toBe("warning");
  });
});

describe('checkSectorCoverage', () => {
  it('passes with enough sectors', () => {
    expect(checkSectorCoverage(makeCandidate({ observedSectorCount: MIN_SECTORS_FOR_DATA })).status).toBe("passed");
  });
  it('fails with too few sectors', () => {
    expect(checkSectorCoverage(makeCandidate({ observedSectorCount: MIN_SECTORS_FOR_DATA - 1 })).status).toBe("failed");
  });
});

describe('checkTransitCount', () => {
  it('passes with enough transits', () => {
    expect(checkTransitCount(makeCandidate({ matrixVisibleTransits: MIN_TRANSITS_FOR_DATA })).status).toBe("passed");
  });
  it('fails with too few transits', () => {
    expect(checkTransitCount(makeCandidate({ matrixVisibleTransits: MIN_TRANSITS_FOR_DATA - 1 })).status).toBe("failed");
  });
  it('falls back to visibleTransits when matrixVisibleTransits missing', () => {
    expect(checkTransitCount(makeCandidate({ matrixVisibleTransits: null, visibleTransits: 5 })).status).toBe("passed");
  });
});

describe('checkOddEven', () => {
  it('passes with OK', () => {
    expect(checkOddEven(makeCandidate({ oddEvenResult: "OK" })).status).toBe("passed");
  });
  it('fails with BAD', () => {
    expect(checkOddEven(makeCandidate({ oddEvenResult: "BAD" })).status).toBe("failed");
  });
  it('warns with BORDERLINE', () => {
    expect(checkOddEven(makeCandidate({ oddEvenResult: "BORDERLINE" })).status).toBe("warning");
  });
  it('warns with UNKNOWN', () => {
    expect(checkOddEven(makeCandidate({ oddEvenResult: "UNKNOWN" })).status).toBe("warning");
  });
});

describe('checkSecondaryEclipse', () => {
  it('passes with NO', () => {
    expect(checkSecondaryEclipse(makeCandidate({ secondaryEclipse: "NO" })).status).toBe("passed");
  });
  it('fails with YES', () => {
    expect(checkSecondaryEclipse(makeCandidate({ secondaryEclipse: "YES" })).status).toBe("failed");
  });
  it('warns with UNKNOWN', () => {
    expect(checkSecondaryEclipse(makeCandidate({ secondaryEclipse: "UNKNOWN" })).status).toBe("warning");
  });
  it('warns with BORDERLINE', () => {
    expect(checkSecondaryEclipse(makeCandidate({ secondaryEclipse: "BORDERLINE" })).status).toBe("warning");
  });
});

describe('checkSapPdcsap', () => {
  it('passes with OK', () => {
    expect(checkSapPdcsap(makeCandidate({ sapPdcsapMatch: "OK" })).status).toBe("passed");
  });
  it('fails with MISMATCH', () => {
    expect(checkSapPdcsap(makeCandidate({ sapPdcsapMatch: "MISMATCH" })).status).toBe("failed");
  });
  it('warns with UNKNOWN', () => {
    expect(checkSapPdcsap(makeCandidate({ sapPdcsapMatch: "UNKNOWN" })).status).toBe("warning");
  });
});

describe('checkActivityRotation', () => {
  it('passes with LOW', () => {
    expect(checkActivityRotation(makeCandidate({ rotationRisk: "LOW" })).status).toBe("passed");
  });
  it('fails with HIGH', () => {
    expect(checkActivityRotation(makeCandidate({ rotationRisk: "HIGH" })).status).toBe("failed");
  });
  it('warns with POSSIBLE', () => {
    expect(checkActivityRotation(makeCandidate({ rotationRisk: "POSSIBLE" })).status).toBe("warning");
  });
  it('warns with UNKNOWN', () => {
    expect(checkActivityRotation(makeCandidate({ rotationRisk: "UNKNOWN" })).status).toBe("warning");
  });
});

describe('SPC_ART Stage 2', () => {
  it('classifies unknown folded light curve as UNCLEAR', () => {
    expect(classifyFoldedLightCurve(makeCandidate({ transitShape: "UNKNOWN" }))).toBe("UNCLEAR");
  });

  it('keeps unclear SPC_ART candidates in PURPLE_SPC_ART with concrete missing checks', () => {
    var result = computeFinalDecision(makeCandidate({
      matrixStatus: "SPC_ART",
      evidenceScore: 55,
      observedSectorCount: 5,
      matrixVisibleTransits: 3,
      transitShape: "UNKNOWN",
      depthStability: "UNKNOWN",
      rotationRisk: "UNKNOWN",
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO"
    }));
    expect(result.status).toBe("PURPLE_SPC_ART");
    expect(result.vettingStage2Class).toBe("PURPLE_SPC_ART");
    expect(result.spcArtStage2.singleTransitStatus).toBe("NEEDS_REVIEW");
    expect(result.spcArtStage2.foldedLightCurveStatus).toBe("UNCLEAR");
    expect(result.spcArtStage2.activityStatus).toBe("UNCLEAR");
    expect(result.spcArtStage2.missingChecks).toContain("Depth stability measurement");
    expect(result.suggestedAction).toContain("Review individual transits");
  });

  it('promotes stable clear SPC_ART candidates into normal recheck flow', () => {
    var stage2 = evaluateSpcArtStage2(makeCandidate({
      matrixStatus: "SPC_ART",
      matrixVisibleTransits: 3,
      transitShape: "U_SHAPE",
      depthStability: "STABLE",
      rotationRisk: "LOW",
      depthPpt: 1.2,
      durationHours: 2.4
    }));
    expect(stage2.recommendation).toBe("PROMOTE_RECHECK");
    expect(stage2.singleTransitStatus).toBe("STABLE");
    expect(stage2.foldedLightCurveStatus).toBe("CLEAR");
  });

  it('marks SPC_ART as RED_FP when the signal is not reproducible', () => {
    var result = computeFinalDecision(makeCandidate({
      matrixStatus: "SPC_ART",
      evidenceScore: 55,
      observedSectorCount: 5,
      matrixVisibleTransits: 1,
      transitShape: "UNKNOWN",
      depthStability: "UNKNOWN",
      rotationRisk: "UNKNOWN",
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO"
    }));
    expect(result.status).toBe("RED_FP");
    expect(result.vettingStage2Class).toBe("RED_FP");
    expect(result.signalStatus).toBe("NOT_REPRODUCIBLE");
    expect(result.failed_test).toBe("Individual Transits");
  });

  it('prefers persisted DATA_BUILD spcArtStage2 over raw matrix UNKNOWN values', () => {
    var persistedStage2 = {
      applies: true,
      source: "DATA_BUILD",
      fallbackUsed: false,
      stage2Completed: true,
      computationStatus: "COMPUTED_WITH_LIMITED_EXPORT_DATA",
      singleTransitStatus: "NEEDS_REVIEW",
      individualTransitStatus: "NEEDS_REVIEW",
      transits: [{ index: 1, status: "NEEDS_REVIEW", flags: [] }],
      individualTransitCount: 85,
      visibleTransits: 41,
      totalTransits: 85,
      medianDepthPpt: 1.59768,
      depthScatterPpt: 0.71895,
      depthStabilityScore: 0.55,
      depthStability: "NOT_COMPUTED",
      rawDepthStability: "UNKNOWN",
      transitShape: "NOT_COMPUTED",
      rawTransitShape: "UNKNOWN",
      foldedLightCurveStatus: "UNCLEAR",
      transitShapeClass: "UNCLEAR",
      activityStatus: "UNCLEAR",
      activityRotationStatus: "UNCLEAR",
      activityFlag: false,
      missingChecks: ["Depth stability measurement"],
      blockingIssues: ["Depth stability metric exists neither in candidate_matrix nor in Stage 2 raw measurements."],
      recommendation: "KEEP_SPC_ART",
      nextAction: "Review individual transits, folded light curve, depth stability, and activity/rotation.",
      plotStatus: "INDIVIDUAL_TRANSIT_PLOTS_NOT_AVAILABLE_IN_DASHBOARD_DATA"
    };
    var result = computeFinalDecision(makeCandidate({
      matrixStatus: "SPC_ART",
      evidenceScore: 66,
      observedSectorCount: 10,
      matrixVisibleTransits: 41,
      matrixTransits: 85,
      transitShape: "UNKNOWN",
      depthStability: "UNKNOWN",
      spcArtStage2: persistedStage2,
      finalDecision: {
        status: "PURPLE_SPC_ART",
        vettingStage2Class: "PURPLE_SPC_ART",
        reason: "Persisted decision",
        check_tree: [{
          name: "Folded Light Curve",
          status: "warning",
          reason: "Transit shape: UNKNOWN, Depth stability: UNKNOWN"
        }]
      }
    }));

    expect(result.spcArtStage2.source).toBe("DATA_BUILD");
    expect(result.spcArtStage2.fallbackUsed).toBe(false);
    expect(result.spcArtStage2.transitShape).toBe("NOT_COMPUTED");
    expect(result.spcArtStage2.depthStability).toBe("NOT_COMPUTED");
    expect(result.spcArtStage2.depthStabilityScore).toBe(0.55);
    expect(result.spcArtStage2.blockingIssues).toContain("Depth stability metric exists neither in candidate_matrix nor in Stage 2 raw measurements.");
    expect(result.check_tree.find((check) => check.name === "Folded Light Curve").reason).toContain("Shape: NOT_COMPUTED");
    expect(result.check_tree.find((check) => check.name === "Depth Stability").reason).toContain("score=0.55");
    expect(result.check_tree.some((check) => check.reason === "Transit shape: UNKNOWN, Depth stability: UNKNOWN")).toBe(false);
  });
});

describe('computeSignalQuality', () => {
  it('returns strong for score >= STRONG_SCORE', () => {
    expect(computeSignalQuality(makeCandidate({ evidenceScore: STRONG_SCORE }))).toBe("strong");
  });
  it('returns medium for score = MEDIUM_SCORE', () => {
    expect(computeSignalQuality(makeCandidate({ evidenceScore: MEDIUM_SCORE }))).toBe("medium");
  });
  it('returns weak for score < MEDIUM_SCORE', () => {
    expect(computeSignalQuality(makeCandidate({ evidenceScore: MEDIUM_SCORE - 1 }))).toBe("weak");
  });
});

describe('computeDataQuality', () => {
  it('returns high for many sectors and transits', () => {
    expect(computeDataQuality(makeCandidate({ observedSectorCount: HIGH_SECTORS, matrixVisibleTransits: HIGH_TRANSITS }))).toBe("high");
  });
  it('returns sufficient for moderate data', () => {
    expect(computeDataQuality(makeCandidate({ observedSectorCount: MIN_SECTORS_FOR_DATA, matrixVisibleTransits: 1 }))).toBe("sufficient");
  });
  it('returns low for poor data', () => {
    expect(computeDataQuality(makeCandidate({ observedSectorCount: MIN_SECTORS_FOR_DATA - 1, matrixVisibleTransits: 0 }))).toBe("low");
  });
});

describe('computeFinalDecision', () => {
  it('returns WAIT_FOR_TESS for no TESS data', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: 0,
      evidenceScore: null,
      astroMonitor: { sectors: [], productsAvailable: false }
    }));
    expect(result.status).toBe("WAIT_FOR_TESS");
    expect(result.vettingStage2Class).toBe("WAIT_FOR_TESS");
    expect(result.signalStatus).toBe("NO_DATA");
    expect(result.dataStatus).toBe("NO_TESS_DATA");
    expect(result.suggestedAction).toBe("Wait for TESS observations");
    expect(result.decisionReason).toBe("No TESS observations available");
    expect(result.failed_test).toBe("TESS Data");
    expect(result.status).not.toBe("NO_PLANET");
    expect(result.status).not.toBe("RED_FP");
    expect(result.not_run_checks).toContain("Vetting Checks");
    expect(result.check_tree.map((item) => item.name)).not.toContain("SAP/PDCSAP");
    expect(result.check_tree.map((item) => item.name)).not.toContain("Odd/Even");
  });

  it('returns LOW_CONFIDENCE for no signal', () => {
    var result = computeFinalDecision(makeCandidate({ evidenceScore: 10 }));
    expect(result.status).toBe("LOW_CONFIDENCE");
    expect(result.failed_test).toBe("Signal Detection");
  });

  it('returns RED_FP for V_SHAPE folded light curve', () => {
    var result = computeFinalDecision(makeCandidate({ transitShape: "V_SHAPE" }));
    expect(result.status).toBe("RED_FP");
    expect(result.failed_test).toBe("Folded Light Curve");
  });

  it('returns DATA_LIMITED_SECTORS for too few sectors', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA - 1,
      evidenceScore: 55,
      transitShape: "U_SHAPE"
    }));
    expect(result.status).toBe("DATA_LIMITED_SECTORS");
    expect(result.failed_test).toBe("Sector Coverage");
  });

  it('returns DATA_LIMITED_TRANSITS for too few transits with enough sectors', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA - 1,
      transitShape: "U_SHAPE",
      evidenceScore: 55
    }));
    expect(result.status).toBe("DATA_LIMITED_TRANSITS");
    expect(result.failed_test).toBe("Transit Count");
  });

  it('returns RED_FP when SAP/PDCSAP mismatch blocks EXOFOP', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: 55,
      sapPdcsapMatch: "MISMATCH"
    }));
    expect(result.status).toBe("RED_FP");
  });

  it('returns RECHECK_ACTIVITY when Activity/Rotation HIGH fails but signal+data are strong', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: 55,
      rotationRisk: "HIGH"
    }));
    expect(result.status).toBe("RECHECK_ACTIVITY");
    expect(result.next_action).toBe("rotation_activity_check");
  });

  it('returns RECHECK_ACTIVITY for STRONG signal + HIGH data + only Activity fail', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: HIGH_SECTORS,
      matrixVisibleTransits: HIGH_TRANSITS,
      transitShape: "U_SHAPE",
      evidenceScore: STRONG_SCORE,
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO",
      rotationRisk: "HIGH"
    }));
    expect(result.status).toBe("RECHECK_ACTIVITY");
    expect(result.reason).toContain("Starker Transit-Kandidat");
  });

  it('returns RED_FP when Secondary Eclipse is detected (hard FP)', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: STRONG_SCORE,
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "YES"
    }));
    expect(result.status).toBe("RED_FP");
    expect(result.reason).toContain("False positive indicator");
  });

  it('returns RED_FP when Odd/Even BAD + SAP/PDCSAP MISMATCH (hard FPs)', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: STRONG_SCORE,
      sapPdcsapMatch: "MISMATCH",
      oddEvenResult: "BAD",
      secondaryEclipse: "NO",
      rotationRisk: "LOW"
    }));
    expect(result.status).toBe("RED_FP");
    expect(result.reason).toContain("False positive indicator");
  });

  it('returns LOW_CONFIDENCE for weak signal + Activity fail', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: MEDIUM_SCORE - 1,
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO",
      rotationRisk: "HIGH"
    }));
    expect(result.status).toBe("LOW_CONFIDENCE");
    expect(result.reason).toContain("Weak signal");
  });

  it('returns GREEN_SPC when all checks pass', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: 55,
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO",
      rotationRisk: "LOW"
    }));
    expect(result.status).toBe("GREEN_SPC");
    expect(result.next_action).toBe("prepare_exofop_upload");
  });

  it('returns NO_PLANET for null candidate', () => {
    var result = computeFinalDecision(null);
    expect(result.status).toBe("NO_PLANET");
  });

  it('returns YELLOW_RECHECK with warning blockers when folded light curve is UNKNOWN', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "UNKNOWN",
      evidenceScore: 55,
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO",
      rotationRisk: "LOW"
    }));
    expect(result.status).toBe("YELLOW_RECHECK");
    expect(result.reason).toContain("Folded Light Curve");
  });

  it('does not overrule with old SPC labels', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: 0,
      matrixVisibleTransits: 0,
      // Old SPC labels should not affect the pipeline decision
      status: "SPC-A",
      matrixStatus: "SPC_ART",
      displayLabels: ["SPC", "SPC_STRONG"]
    }));
    expect(result.status).toBe("WAIT_FOR_TESS");
    expect(result.vettingStage2Class).toBe("WAIT_FOR_TESS");
    expect(result.failed_test).toBe("TESS Data");
  });

  it('produces check_tree with all 9 checks', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: MIN_SECTORS_FOR_DATA,
      matrixVisibleTransits: MIN_TRANSITS_FOR_DATA,
      transitShape: "U_SHAPE",
      evidenceScore: 55,
      sapPdcsapMatch: "OK",
      oddEvenResult: "OK",
      secondaryEclipse: "NO",
      rotationRisk: "LOW"
    }));
    expect(result.check_tree.length).toBe(9);
    expect(result.check_tree[0].name).toBe("TESS Data");
    expect(result.check_tree[8].name).toBe("Activity/Rotation");
  });

  it('produces blockers listing all failing checks', () => {
    var result = computeFinalDecision(makeCandidate({
      observedSectorCount: 0,
      matrixVisibleTransits: 0
    }));
    expect(result.blockers.length).toBeGreaterThan(0);
  });
});
