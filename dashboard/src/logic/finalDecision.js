// Thresholds match config/pipeline_thresholds.json
export const MIN_SECTORS_FOR_DATA = 2;
export const MIN_TRANSITS_FOR_DATA = 3;
export const STRONG_SCORE = 65;
export const MEDIUM_SCORE = 40;
export const HIGH_SECTORS = 8;
export const HIGH_TRANSITS = 3;
export const SIGNAL_MIN_SCORE = 20;

export function checkTessData(candidate) {
  const sectors = candidate.observedSectorCount || candidate.astroMonitor?.sectors?.length || 0;
  const productsAvailable = candidate.astroMonitor
    ? candidate.astroMonitor.productsAvailable !== false
    : true;
  if (sectors <= 0 || !productsAvailable) {
    return { status: "failed", reason: "No TESS sectors available" };
  }
  return { status: "passed", reason: `${sectors} TESS sector(s) available` };
}

export function checkSignalDetection(candidate) {
  const score = candidate.evidenceScore;
  if (score === null || score === undefined || score < SIGNAL_MIN_SCORE) {
    return { status: "failed", reason: "No BLS/TLS signal detected" };
  }
  return { status: "passed", reason: `BLS/TLS signal detected (Score: ${score})` };
}

export function checkFoldedLightCurve(candidate) {
  const shape = (candidate.transitShape || "").toUpperCase();
  const missingShapeStatuses = ["UNKNOWN", "NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS", ""];
  if (shape === "V_SHAPE") {
    return { status: "failed", reason: "V-shape transit suggests EB而非 planet" };
  }
  if (missingShapeStatuses.includes(shape) || !shape) {
    return { status: "warning", reason: "Transit shape " + (shape || "UNKNOWN") + "; needs Stage 2 review" };
  }
  if (shape === "ASYMMETRIC") {
    return { status: "warning", reason: "Asymmetric transit shape; possible blend or grazing" };
  }
  return { status: "passed", reason: "Transit shape: " + shape };
}

export function checkSectorCoverage(candidate) {
  const sectors = candidate.observedSectorCount || 0;
  if (sectors < MIN_SECTORS_FOR_DATA) {
    return { status: "failed", reason: sectors + " sector(s), need " + MIN_SECTORS_FOR_DATA + "+" };
  }
  return { status: "passed", reason: sectors + " sector(s) available" };
}

export function checkTransitCount(candidate) {
  const transits = candidate.matrixVisibleTransits || candidate.visibleTransits || 0;
  if (transits < MIN_TRANSITS_FOR_DATA) {
    return { status: "failed", reason: transits + " visible transit(s), need " + MIN_TRANSITS_FOR_DATA + "+" };
  }
  return { status: "passed", reason: transits + " visible transit(s)" };
}

export function checkOddEven(candidate) {
  const result = (candidate.oddEvenResult || "").toUpperCase();
  if (result === "BAD") {
    return { status: "failed", reason: "Odd/Even inconsistent" };
  }
  if (result === "BORDERLINE" || result === "UNKNOWN" || result === "") {
    return { status: "warning", reason: "Odd/Even: " + (result || "not run") };
  }
  return { status: "passed", reason: "Odd/Even consistent" };
}

export function checkSecondaryEclipse(candidate) {
  const result = (candidate.secondaryEclipse || "").toUpperCase();
  if (result === "YES") {
    return { status: "failed", reason: "Secondary eclipse detected" };
  }
  if (result === "UNKNOWN" || result === "BORDERLINE" || result === "") {
    return { status: "warning", reason: "Secondary eclipse: " + (result || "not checked") };
  }
  return { status: "passed", reason: "No secondary eclipse" };
}

export function checkSapPdcsap(candidate) {
  const result = (candidate.sapPdcsapMatch || "").toUpperCase();
  if (result === "MISMATCH") {
    return { status: "failed", reason: "SAP/PDCSAP mismatch" };
  }
  if (result === "UNKNOWN" || result === "") {
    return { status: "warning", reason: "SAP/PDCSAP not compared" };
  }
  return { status: "passed", reason: "SAP/PDCSAP consistent" };
}

export function checkActivityRotation(candidate) {
  const risk = (candidate.rotationRisk || "").toUpperCase();
  if (risk === "HIGH" || risk === "FAST_ROTATION_ACTIVITY_RECHECK") {
    return { status: "failed", reason: "High rotation/activity risk" };
  }
  if (risk === "POSSIBLE" || risk === "UNKNOWN" || risk === "") {
    return { status: "warning", reason: "Rotation risk: " + (risk || "not assessed") };
  }
  return { status: "passed", reason: "Rotation risk: low" };
}

export function isSpcArtCandidate(candidate) {
  const text = [
    candidate.matrixStatus,
    candidate.matrixClass,
    candidate.status,
    candidate.reason,
    candidate.decisionReason,
    candidate.nextStep,
    candidate.notes,
    ...(candidate.displayLabels || [])
  ].join(" ").toUpperCase();
  return /SPC_ART|ARTIFACT|SYSTEMATIC|SYSTEMATICS/.test(text);
}

export function classifyFoldedLightCurve(candidate) {
  const shape = (candidate.transitShape || "").toUpperCase();
  const depthStability = (candidate.depthStability || "").toUpperCase();
  if (["SHAPE_CLEAR", "U_SHAPE", "U_SHAPED", "BOX", "BOX_SHAPED", "CLEAR"].includes(shape)) return "CLEAR";
  if (["V_SHAPE", "V_SHAPED"].includes(shape)) return "V_SHAPED";
  if (["NOISE", "NOISY"].includes(shape)) return "NOISY";
  if (["ARTIFACT", "ARTIFACT_LIKE", "SPURIOUS", "INVERTED", "IRREGULAR", "INVALID"].includes(shape)) return "ARTIFACT_LIKE";
  if (depthStability === "UNSTABLE" || depthStability === "HIGH_VARIABILITY") return "ARTIFACT_LIKE";
  return "UNCLEAR";
}

function normalizeStage2MissingStatus(value, candidate, minTransits = 2) {
  const status = String(value || "").toUpperCase();
  if (status && !["UNKNOWN", "NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS"].includes(status)) {
    return status;
  }
  const visibleTransits = Number(candidate.matrixVisibleTransits ?? candidate.visibleTransits ?? 0) || 0;
  const hasLightcurveProduct = Boolean(candidate.lightcurveImg || candidate.lightcurveImgDeploy || candidate.astroMonitor?.productsAvailable);
  if (visibleTransits < minTransits) return "INSUFFICIENT_TRANSITS";
  if (!hasLightcurveProduct) return "MISSING_RAW_DATA";
  return "NOT_COMPUTED";
}

function classifySingleTransitStability(stats) {
  const visibleCount = Number(stats.visibleTransitCount ?? stats.visible_transit_count ?? 0) || 0;
  const minDepthRatio = Number(stats.minDepthRatio ?? stats.min_depth_ratio ?? NaN);
  const depthCv = Number(stats.depthCv ?? stats.depth_cv ?? NaN);
  if (visibleCount < 2) return "INSUFFICIENT_TRANSITS";
  if (Number.isFinite(minDepthRatio) && minDepthRatio < 0.35) return "UNSTABLE";
  if (Number.isFinite(depthCv) && depthCv > 0.75) return "UNSTABLE";
  if (Number.isFinite(minDepthRatio) && minDepthRatio < 0.6) return "BORDERLINE";
  if (Number.isFinite(depthCv) && depthCv > 0.5) return "BORDERLINE";
  return "STABLE";
}

function singleTransitScore(stats) {
  const stability = String(stats.depthStability || stats.depth_stability || classifySingleTransitStability(stats)).toUpperCase();
  if (stability === "STABLE") return 1;
  if (stability === "BORDERLINE") return 0.55;
  if (stability === "UNSTABLE") return 0;
  return 0.5;
}

function getStoredSpcArtStage2(candidate) {
  const stage2 = candidate?.spcArtStage2 || candidate?.finalDecision?.spcArtStage2;
  if (!stage2 || !stage2.applies) return null;
  return {
    ...stage2,
    source: stage2.source || "DATA_BUILD",
    fallbackUsed: Boolean(stage2.fallbackUsed),
    stage2Completed: stage2.stage2Completed !== false,
    blockingIssues: stage2.blockingIssues || stage2.missingChecks || []
  };
}

function stage2CheckStatus(stage2) {
  if (stage2.recommendation === "FALSE_POSITIVE") return "failed";
  if (stage2.recommendation === "PROMOTE_RECHECK") return "passed";
  return "warning";
}

function depthStage2CheckStatus(stage2) {
  const score = Number(stage2.depthStabilityScore ?? 0);
  if (score >= 0.65) return "passed";
  if (score < 0.4) return "failed";
  return "warning";
}

function individualStage2CheckStatus(stage2) {
  if (stage2.singleTransitStatus === "STABLE") return "passed";
  if (stage2.singleTransitStatus === "NOT_REPRODUCIBLE") return "failed";
  return "warning";
}

function withStoredSpcArtStage2Decision(decision, stage2) {
  const existingTree = Array.isArray(decision.check_tree) ? decision.check_tree : [];
  const keptTree = existingTree.filter((check) => ![
    "Folded Light Curve",
    "Individual Transits",
    "Depth Stability",
    "SPC_ART Stage 2"
  ].includes(check.name));
  const enrichedTree = [
    ...keptTree,
    {
      name: "Folded Light Curve",
      status: stage2CheckStatus(stage2),
      reason: "Folded LC: " + (stage2.foldedLightCurveStatus || "-") + "; Shape: " + (stage2.transitShape || stage2.transitShapeClass || "-") + "; Depth: " + (stage2.depthStability || "-")
    },
    {
      name: "Individual Transits",
      status: individualStage2CheckStatus(stage2),
      reason: (stage2.singleTransitStatus || "-") + "; " + (stage2.plotStatus || "-")
    },
    {
      name: "Depth Stability",
      status: depthStage2CheckStatus(stage2),
      reason: "median=" + (stage2.medianDepthPpt ?? "-") + " ppt, scatter=" + (stage2.depthScatterPpt ?? "-") + ", score=" + (stage2.depthStabilityScore ?? "-")
    },
    {
      name: "SPC_ART Stage 2",
      status: stage2CheckStatus(stage2),
      reason: "Source: " + (stage2.source || "DATA_BUILD") + "; fallback=" + (stage2.fallbackUsed ? "yes" : "no") + "; " + (stage2.computationStatus || "COMPUTED")
    }
  ];
  return {
    ...decision,
    spcArtStage2: stage2,
    warnings: stage2.missingChecks || decision.warnings || [],
    blockers: stage2.blockingIssues || stage2.missingChecks || decision.blockers || [],
    check_tree: enrichedTree
  };
}

export function evaluateSpcArtStage2(candidate) {
  const individualStats = candidate.individualTransitStatistics || candidate.individual_transit_statistics || {};
  const individualEvents = candidate.individualTransitEvents || candidate.individual_transit_events || [];
  const visibleTransits = Number(candidate.matrixVisibleTransits ?? candidate.visibleTransits ?? candidate.matrixTransits ?? candidate.transits ?? 0) || 0;
  const expectedTransits = Number(candidate.matrixTransits ?? candidate.transits ?? visibleTransits) || visibleTransits;
  const depthPpt = Number(candidate.depthPpt ?? 0) || 0;
  const durationHours = Number(candidate.durationHours ?? 0) || 0;
  const depthStability = (candidate.depthStability || "").toUpperCase();
  const depthStabilityStatus = normalizeStage2MissingStatus(depthStability, candidate);
  const transitShapeStatus = normalizeStage2MissingStatus(candidate.transitShape, candidate);
  const shapeClass = classifyFoldedLightCurve(candidate);
  const transitShapeScore = candidate.transitShapeScore ?? candidate.foldedLightCurveShape?.transitShapeScore ?? null;
  const transitShapeSource = candidate.transitShapeSource || candidate.foldedLightCurveShape?.transitShapeSource || "";
  const shapeBlockingIssues = candidate.foldedLightCurveShape?.shapeBlockingIssues || [];
  const activityRisk = (candidate.rotationRisk || "").toUpperCase();
  const sectorEdgeRisk = (candidate.sectorEdgeRisk || "").toUpperCase();
  const dataGapRisk = (candidate.dataGapRisk || "").toUpperCase();

  if (Array.isArray(individualEvents) && individualEvents.length) {
    const depthStabilityScore = singleTransitScore(individualStats);
    const visibleFromStats = Number(individualStats.visibleTransitCount ?? individualStats.visible_transit_count ?? 0) || individualEvents.filter((event) => event.visible).length;
    const totalFromStats = Number(individualStats.individualTransitCount ?? individualStats.individual_transit_count ?? 0) || individualEvents.length;
    const depthStabilityStatus = String(individualStats.depthStability || individualStats.depth_stability || classifySingleTransitStability(individualStats)).toUpperCase();
    const transitStatus = individualEvents.map((event, index) => {
      const localSnr = Number(event.localSnr ?? event.local_snr ?? NaN);
      const visible = Boolean(event.visible);
      const flags = [];
      if (!visible) flags.push("missing_or_not_visible");
      if (Number.isFinite(localSnr) && localSnr < 5) flags.push("low_single_transit_snr");
      if (sectorEdgeRisk === "HIGH" || dataGapRisk === "HIGH") flags.push("edge_or_gap_risk");
      if (depthStabilityScore < 0.4) flags.push("depth_outlier_possible");
      return {
        index: index + 1,
        epoch: event.epoch,
        expectedTime: event.expectedTime ?? event.expected_time,
        status: visible && !flags.length ? "OK" : (visible ? "NEEDS_REVIEW" : "MISSING"),
        depthPpt: event.depthPpt ?? event.depth_ppt ?? null,
        localSnr: Number.isFinite(localSnr) ? localSnr : null,
        nIn: event.nIn ?? event.n_in ?? null,
        nOut: event.nOut ?? event.n_out ?? null,
        visible,
        flags
      };
    });
    const missingChecks = [];
    if (visibleFromStats < 2) missingChecks.push("Signal reproducibility");
    if (shapeClass === "UNCLEAR") missingChecks.push("Folded Light Curve classification");
    if (["UNKNOWN", "NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS", ""].includes(depthStabilityStatus)) missingChecks.push("Depth stability measurement");
    if (activityRisk === "UNKNOWN" || activityRisk === "" || activityRisk === "POSSIBLE") missingChecks.push("Activity/Rotation check");
    if (transitStatus.some((item) => item.status !== "OK")) missingChecks.push("Individual transit review");
    const blockingIssues = [];
    if (transitShapeStatus === "MISSING_RAW_DATA") blockingIssues.push("Transit shape not computed because raw folded-light-curve metrics are missing from the data export.");
    else if (transitShapeStatus === "INSUFFICIENT_TRANSITS") blockingIssues.push("Transit shape not computed because fewer than two visible transits are available.");
    else if (transitShapeStatus === "NOT_COMPUTED") blockingIssues.push("Transit shape metric exists neither in candidate_matrix nor in Stage 2 raw measurements.");
    blockingIssues.push(...shapeBlockingIssues);
    const plotStatus = individualStats.plotStatus || candidate.individualTransitPlotStatus || "PLOT_NOT_AVAILABLE";
    if (plotStatus === "PLOT_NOT_AVAILABLE") missingChecks.push("PLOT_NOT_AVAILABLE");
    const activityFlag = ["HIGH", "STRONG", "FAST_ROTATION_ACTIVITY_RECHECK"].includes(activityRisk);
    const activityStatus = activityFlag ? "FLAGGED" : (["LOW", "NONE", "OK", "NO"].includes(activityRisk) ? "LOW_RISK" : "UNCLEAR");
    const stableIndividualTransits = visibleFromStats >= 2 && depthStabilityScore >= 0.65 && transitStatus.every((item) => item.status !== "MISSING");
    const reproducible = visibleFromStats >= 2;
    const artifactConcern = shapeClass === "ARTIFACT_LIKE" || depthStabilityScore < 0.4 || activityFlag || sectorEdgeRisk === "HIGH" || dataGapRisk === "HIGH";
    let recommendation = "KEEP_SPC_ART";
    let nextAction = "Review individual transits, folded light curve, depth stability, and activity/rotation.";
    if (!reproducible) {
      recommendation = "FALSE_POSITIVE";
      nextAction = "Mark as false positive unless new data reproduces the signal.";
    } else if (stableIndividualTransits && shapeClass === "CLEAR" && activityStatus === "LOW_RISK") {
      recommendation = "PROMOTE_RECHECK";
      nextAction = "Move to recheck/SPC preparation after documenting Stage 2 evidence.";
    } else if (artifactConcern) {
      recommendation = "KEEP_SPC_ART";
      nextAction = "Keep SPC_ART and resolve artifact/systematics concerns before follow-up.";
    }
    return {
      applies: true,
      source: "LEVEL5_SINGLE_TRANSITS",
      fallbackUsed: false,
      stage2Completed: true,
      computationStatus: blockingIssues.length ? "COMPUTED_WITH_LIMITED_EXPORT_DATA" : "COMPUTED",
      blockingIssues,
      singleTransitStatus: reproducible ? (stableIndividualTransits ? "STABLE" : "NEEDS_REVIEW") : "NOT_REPRODUCIBLE",
      individualTransitStatus: reproducible ? (stableIndividualTransits ? "STABLE" : "NEEDS_REVIEW") : "NOT_REPRODUCIBLE",
      transits: transitStatus,
      individualTransitCount: transitStatus.length,
      visibleTransits: visibleFromStats,
      totalTransits: totalFromStats,
      medianDepthPpt: individualStats.medianDepthPpt ?? individualStats.median_depth_ppt ?? null,
      depthScatterPpt: individualStats.depthScatterPpt ?? individualStats.depth_scatter_ppt ?? null,
      medianSingleTransitSnr: individualStats.medianSingleTransitSnr ?? individualStats.median_single_transit_snr ?? null,
      depthStabilityScore,
      depthStability: depthStabilityStatus,
      rawDepthStability: depthStabilityStatus || "UNKNOWN",
      transitShape: transitShapeStatus,
      rawTransitShape: candidate.rawTransitShape || candidate.transitShape || "UNKNOWN",
      transitShapeScore,
      transitShapeSource,
      shapeBlockingIssues,
      foldedLightCurveStatus: shapeClass,
      transitShapeClass: shapeClass,
      activityStatus,
      activityRotationStatus: activityStatus,
      activityFlag,
      missingChecks: [...new Set(missingChecks)],
      recommendation,
      nextAction,
      plotStatus,
      individualTransitPlotPath: individualStats.individualTransitPlotPath || candidate.individualTransitPlotPath || "",
      individualTransitStatistics: individualStats,
      individualTransitEvents: individualEvents
    };
  }

  let depthStabilityScore = 0.5;
  if (["STABLE", "LOW", "OK", "GOOD"].includes(depthStability)) depthStabilityScore = 1;
  else if (["UNSTABLE", "HIGH_VARIABILITY"].includes(depthStability)) depthStabilityScore = 0;
  else if (depthPpt > 0 && visibleTransits >= 3) depthStabilityScore = 0.55;

  const transitStatus = [];
  const count = Math.max(expectedTransits, visibleTransits, 0);
  for (let i = 0; i < count; i += 1) {
    let status = i < visibleTransits ? "NEEDS_REVIEW" : "MISSING";
    const flags = [];
    if (i >= visibleTransits) flags.push("missing_or_not_visible");
    if (sectorEdgeRisk === "HIGH" || dataGapRisk === "HIGH") flags.push("edge_or_gap_risk");
    if (depthStabilityScore < 0.4) flags.push("depth_outlier_possible");
    transitStatus.push({
      index: i + 1,
      status,
      depthPpt: depthPpt || null,
      durationHours: durationHours || null,
      flags
    });
  }

  const missingChecks = [];
  if (visibleTransits < 2) missingChecks.push("Signal reproducibility");
  if (shapeClass === "UNCLEAR") missingChecks.push("Folded Light Curve classification");
  if (["UNKNOWN", "NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS", ""].includes(depthStabilityStatus)) missingChecks.push("Depth stability measurement");
  if (activityRisk === "UNKNOWN" || activityRisk === "" || activityRisk === "POSSIBLE") missingChecks.push("Activity/Rotation check");
  if (transitStatus.some((item) => item.status !== "OK")) missingChecks.push("Individual transit review");

  const blockingIssues = [];
  if (transitShapeStatus === "MISSING_RAW_DATA") blockingIssues.push("Transit shape not computed because raw folded-light-curve metrics are missing from the data export.");
  else if (transitShapeStatus === "INSUFFICIENT_TRANSITS") blockingIssues.push("Transit shape not computed because fewer than two visible transits are available.");
  else if (transitShapeStatus === "NOT_COMPUTED") blockingIssues.push("Transit shape metric exists neither in candidate_matrix nor in Stage 2 raw measurements.");
  blockingIssues.push(...shapeBlockingIssues);
  if (depthStabilityStatus === "MISSING_RAW_DATA") blockingIssues.push("Depth stability not computed because individual-transit depth measurements are missing from the data export.");
  else if (depthStabilityStatus === "INSUFFICIENT_TRANSITS") blockingIssues.push("Depth stability not computed because fewer than two visible transits are available.");
  else if (depthStabilityStatus === "NOT_COMPUTED") blockingIssues.push("Depth stability metric exists neither in candidate_matrix nor in Stage 2 raw measurements.");

  const activityFlag = ["HIGH", "STRONG", "FAST_ROTATION_ACTIVITY_RECHECK"].includes(activityRisk);
  const activityStatus = activityFlag ? "FLAGGED" : (["LOW", "NONE", "OK", "NO"].includes(activityRisk) ? "LOW_RISK" : "UNCLEAR");
  const depthScatterPpt = depthStabilityScore === 1 ? 0 : (depthPpt ? Number((depthPpt * (1 - depthStabilityScore)).toFixed(4)) : null);
  const stableIndividualTransits = visibleTransits >= 2 && depthStabilityScore >= 0.65 && transitStatus.every((item) => item.status !== "MISSING");
  const clearFolded = shapeClass === "CLEAR";
  const artifactConcern = shapeClass === "ARTIFACT_LIKE" || depthStabilityScore < 0.4 || activityFlag || sectorEdgeRisk === "HIGH" || dataGapRisk === "HIGH";
  const reproducible = visibleTransits >= 2;

  let recommendation = "KEEP_SPC_ART";
  let nextAction = "Review individual transits, folded light curve, depth stability, and activity/rotation.";
  if (!reproducible) {
    recommendation = "FALSE_POSITIVE";
    nextAction = "Mark as false positive unless new data reproduces the signal.";
  } else if (stableIndividualTransits && clearFolded && activityStatus === "LOW_RISK") {
    recommendation = "PROMOTE_RECHECK";
    nextAction = "Move to recheck/SPC preparation after documenting Stage 2 evidence.";
  } else if (artifactConcern) {
    recommendation = "KEEP_SPC_ART";
    nextAction = "Keep SPC_ART and resolve artifact/systematics concerns before follow-up.";
  }

  return {
    applies: true,
    source: "RUNTIME_FALLBACK",
    fallbackUsed: true,
    stage2Completed: true,
    computationStatus: blockingIssues.length ? "COMPUTED_WITH_LIMITED_EXPORT_DATA" : "COMPUTED",
    blockingIssues,
    singleTransitStatus: reproducible ? (stableIndividualTransits ? "STABLE" : "NEEDS_REVIEW") : "NOT_REPRODUCIBLE",
    individualTransitStatus: reproducible ? (stableIndividualTransits ? "STABLE" : "NEEDS_REVIEW") : "NOT_REPRODUCIBLE",
    transits: transitStatus,
    individualTransitCount: transitStatus.length,
    visibleTransits,
    totalTransits: expectedTransits,
    medianDepthPpt: depthPpt || null,
    depthScatterPpt,
    depthStabilityScore,
    depthStability: depthStabilityStatus,
    rawDepthStability: candidate.rawDepthStability || depthStability || "UNKNOWN",
    transitShape: transitShapeStatus,
    rawTransitShape: candidate.rawTransitShape || candidate.transitShape || "UNKNOWN",
    transitShapeScore,
    transitShapeSource,
    shapeBlockingIssues,
    foldedLightCurveStatus: shapeClass,
    transitShapeClass: shapeClass,
    activityStatus,
    activityRotationStatus: activityStatus,
    activityFlag,
    missingChecks: [...new Set(missingChecks)],
    recommendation,
    nextAction,
    plotStatus: "INDIVIDUAL_TRANSIT_PLOTS_NOT_AVAILABLE_IN_DASHBOARD_DATA"
  };
}

export function computeSignalQuality(candidate) {
  const score = candidate.evidenceScore || 0;
  if (score >= STRONG_SCORE) return "strong";
  if (score >= MEDIUM_SCORE) return "medium";
  return "weak";
}

export function computeDataQuality(candidate) {
  const sectors = candidate.observedSectorCount || 0;
  const transits = candidate.matrixVisibleTransits || candidate.visibleTransits || 0;
  if (sectors >= HIGH_SECTORS && transits >= HIGH_TRANSITS) return "high";
  if (sectors >= MIN_SECTORS_FOR_DATA && transits >= 1) return "sufficient";
  return "low";
}

export function runAllChecks(candidate) {
  return {
    "TESS Data": checkTessData(candidate),
    "Signal Detection": checkSignalDetection(candidate),
    "Folded Light Curve": checkFoldedLightCurve(candidate),
    "Sector Coverage": checkSectorCoverage(candidate),
    "Transit Count": checkTransitCount(candidate),
    "Odd/Even": checkOddEven(candidate),
    "Secondary Eclipse": checkSecondaryEclipse(candidate),
    "SAP/PDCSAP": checkSapPdcsap(candidate),
    "Activity/Rotation": checkActivityRotation(candidate)
  };
}

export function categorizeChecks(checks) {
  const passed = [];
  const warning = [];
  const failed = [];
  const notRun = [];
  const blockers = [];
  for (const [name, result] of Object.entries(checks)) {
    if (result.status === "passed") passed.push(name);
    else if (result.status === "warning") warning.push(name);
    else if (result.status === "failed") failed.push(name);
    else notRun.push(name);
    if (result.status !== "passed") {
      blockers.push({ check: name, reason: result.reason });
    }
  }
  return { passed, warning, failed, notRun, blockers };
}

export function determineMatrixCell(signalQuality, dataQuality, status) {
  if (status === "WAIT_FOR_TESS") {
    return "no_tess_data";
  }
  if (status === "NO_PLANET") {
    return "no_planet";
  }
  if (status === "DATA_LIMITED_SECTORS") {
    return "data_limited_sectors";
  }
  if (status === "DATA_LIMITED_TRANSITS") {
    return "data_limited_transits";
  }
  if (signalQuality === "strong" && dataQuality === "high") return "strong_high";
  if (signalQuality === "strong" && dataQuality === "sufficient") return "strong_sufficient";
  if (signalQuality === "medium" && dataQuality === "high") return "medium_high";
  return signalQuality + "_" + dataQuality;
}

export function computeFinalDecision(candidate) {
  if (!candidate || typeof candidate !== "object") {
    return {
      status: "NO_PLANET",
      reason: "No candidate data available",
      failed_test: "Candidate",
      next_action: "exclude",
      signal_quality: "weak",
      data_quality: "low",
      matrix_cell: "no_data",
      passed_checks: [],
      warning_checks: [],
      failed_checks: [],
      not_run_checks: ["TESS Data", "Signal Detection", "Folded Light Curve", "Sector Coverage", "Transit Count", "Odd/Even", "Secondary Eclipse", "SAP/PDCSAP", "Activity/Rotation"],
      blockers: [],
      check_tree: []
    };
  }

  const storedSpcArtStage2 = getStoredSpcArtStage2(candidate);
  const needsSpcArtStage2 = isSpcArtCandidate(candidate) && !storedSpcArtStage2;
  if (candidate.finalDecision && candidate.finalDecision.vettingStage2Class && !needsSpcArtStage2) {
    return storedSpcArtStage2
      ? withStoredSpcArtStage2Decision(candidate.finalDecision, storedSpcArtStage2)
      : candidate.finalDecision;
  }

  const tessCheck = checkTessData(candidate);
  if (tessCheck.status === "failed") {
    return {
      ticId: candidate.tic,
      status: "WAIT_FOR_TESS",
      vettingStage2Class: "WAIT_FOR_TESS",
      reason: "No TESS observations available.",
      decisionReason: "No TESS observations available",
      failed_test: "TESS Data",
      next_action: "wait_for_tess",
      suggestedAction: "Wait for TESS observations",
      signal_quality: "unknown",
      signalStatus: "NO_DATA",
      data_quality: "low",
      dataStatus: "NO_TESS_DATA",
      monitorStatus: "NO_TESS_DATA",
      matrix_cell: "no_tess_data",
      scoreDelta: 0,
      badges: ["WAIT_FOR_TESS", "NO_TESS_DATA"],
      warnings: ["No TESS data available"],
      passed_checks: [],
      warning_checks: [],
      failed_checks: ["TESS Data"],
      not_run_checks: ["Signal Detection", "Folded Light Curve", "Sector Coverage", "Transit Count", "Vetting Checks"],
      blockers: ["No TESS data available"],
      check_tree: [{ name: "TESS Data", status: "failed", reason: "No TESS sectors available" }]
    };
  }

  const checks = runAllChecks(candidate);
  const cats = categorizeChecks(checks);
  const signalQuality = computeSignalQuality(candidate);
  const dataQuality = computeDataQuality(candidate);
  const spcArtStage2 = isSpcArtCandidate(candidate) ? (storedSpcArtStage2 || evaluateSpcArtStage2(candidate)) : null;

  const checkTree = Object.entries(checks).map(([name, result]) => ({
    name,
    status: result.status,
    reason: result.reason
  }));

  // Step 1-3: NO_PLANET conditions
  if (checks["TESS Data"].status === "failed") {
    return {
      status: "NO_PLANET",
      reason: "No TESS observations available.",
      failed_test: "TESS Data",
      next_action: "wait_for_tess",
      signal_quality: signalQuality,
      data_quality: "low",
      matrix_cell: determineMatrixCell(signalQuality, "low", "NO_PLANET"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  if (checks["Signal Detection"].status === "failed") {
    return {
      status: "LOW_CONFIDENCE",
      vettingStage2Class: "LOW_CONFIDENCE",
      reason: "No BLS/TLS signal detected.",
      failed_test: "Signal Detection",
      next_action: "manual_review_required",
      suggestedAction: "Signal detection failed.",
      decisionReason: "No BLS/TLS signal detected.",
      signalStatus: "NO_SIGNAL",
      dataStatus: "TESS_DATA_AVAILABLE",
      monitorStatus: "TESS_DATA_AVAILABLE",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "LOW_CONFIDENCE"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  if (checks["Folded Light Curve"].status === "failed") {
    return {
      status: "RED_FP",
      vettingStage2Class: "RED_FP",
      reason: "Folded light curve indicates EB or artifact.",
      decisionReason: "Folded light curve indicates EB or artifact.",
      failed_test: "Folded Light Curve",
      next_action: "exclude",
      suggestedAction: "Candidate excluded from follow-up.",
      signalStatus: "VISIBLE_SIGNAL",
      dataStatus: "TESS_DATA_AVAILABLE",
      monitorStatus: "TESS_DATA_AVAILABLE",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: "false_positive",
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  if (spcArtStage2) {
    checkTree.push(
      {
        name: "Individual Transits",
        status: spcArtStage2.singleTransitStatus === "STABLE" ? "passed" : (spcArtStage2.singleTransitStatus === "NOT_REPRODUCIBLE" ? "failed" : "warning"),
        reason: spcArtStage2.singleTransitStatus + "; " + spcArtStage2.plotStatus
      },
      {
        name: "Depth Stability",
        status: spcArtStage2.depthStabilityScore >= 0.65 ? "passed" : (spcArtStage2.depthStabilityScore < 0.4 ? "failed" : "warning"),
        reason: "median=" + (spcArtStage2.medianDepthPpt ?? "-") + " ppt, scatter=" + (spcArtStage2.depthScatterPpt ?? "-") + ", score=" + spcArtStage2.depthStabilityScore
      },
      {
        name: "SPC_ART Stage 2",
        status: spcArtStage2.recommendation === "PROMOTE_RECHECK" ? "passed" : (spcArtStage2.recommendation === "FALSE_POSITIVE" ? "failed" : "warning"),
        reason: "Folded LC: " + spcArtStage2.foldedLightCurveStatus + "; Activity: " + spcArtStage2.activityStatus
      }
    );

    if (spcArtStage2.recommendation === "FALSE_POSITIVE") {
      return {
        status: "RED_FP",
        vettingStage2Class: "RED_FP",
        reason: "SPC_ART Stage 2: signal is not reproducible in individual transits.",
        decisionReason: "SPC_ART Stage 2: signal is not reproducible in individual transits.",
        failed_test: "Individual Transits",
        next_action: "exclude",
        suggestedAction: spcArtStage2.nextAction,
        signalStatus: "NOT_REPRODUCIBLE",
        dataStatus: "TESS_DATA_AVAILABLE",
        monitorStatus: "TESS_DATA_AVAILABLE",
        signal_quality: signalQuality,
        data_quality: dataQuality,
        matrix_cell: "false_positive",
        scoreDelta: 0,
        badges: ["RED_FP", "SPC_ART_STAGE2"],
        warnings: spcArtStage2.missingChecks,
        spcArtStage2,
        passed_checks: cats.passed,
        warning_checks: cats.warning,
        failed_checks: [...cats.failed, "Individual Transits"],
        not_run_checks: cats.notRun,
        blockers: ["Signal not reproducible", ...spcArtStage2.missingChecks],
        check_tree: checkTree
      };
    }

    if (spcArtStage2.recommendation !== "PROMOTE_RECHECK") {
      return {
        status: "PURPLE_SPC_ART",
        vettingStage2Class: "PURPLE_SPC_ART",
        reason: "SPC_ART Stage 2 required: artifact/systematics concerns remain.",
        decisionReason: "SPC_ART Stage 2 required: " + (spcArtStage2.missingChecks.length ? spcArtStage2.missingChecks.join(", ") : "artifact/systematics concerns remain") + ".",
        failed_test: "SPC_ART Stage 2",
        next_action: "manual_review_required",
        suggestedAction: spcArtStage2.nextAction,
        signalStatus: "VISIBLE_SIGNAL",
        dataStatus: "TESS_DATA_AVAILABLE",
        monitorStatus: "TESS_DATA_AVAILABLE",
        signal_quality: signalQuality,
        data_quality: dataQuality,
        matrix_cell: "artifact_recheck",
        scoreDelta: 0,
        badges: ["PURPLE_SPC_ART", "SPC_ART_STAGE2"],
        warnings: spcArtStage2.missingChecks,
        spcArtStage2,
        passed_checks: cats.passed,
        warning_checks: [...new Set([...cats.warning, "SPC_ART Stage 2"])],
        failed_checks: cats.failed,
        not_run_checks: cats.notRun,
        blockers: spcArtStage2.missingChecks,
        check_tree: checkTree
      };
    }
  }

  // Step 5: Sector coverage
  if (checks["Sector Coverage"].status === "failed") {
    return {
      status: "DATA_LIMITED_SECTORS",
      reason: "Insufficient sector coverage for reliable transit detection.",
      failed_test: "Sector Coverage",
      next_action: "wait_for_more_sectors",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "DATA_LIMITED_SECTORS"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  // Step 6: Transit count
  if (checks["Transit Count"].status === "failed") {
    return {
      status: "DATA_LIMITED_TRANSITS",
      reason: "Insufficient observed transits for reliable assessment.",
      failed_test: "Transit Count",
      next_action: "wait_for_more_transits",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "DATA_LIMITED_TRANSITS"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  // Step 7a: Hard vetting — definitive false positive indicators
  const hardVettingChecks = ["Odd/Even", "Secondary Eclipse", "SAP/PDCSAP"];
  const hardVettingFails = hardVettingChecks.filter(function(name) { return checks[name].status === "failed"; });
  if (hardVettingFails.length > 0) {
    return {
      status: "RED_FP",
      vettingStage2Class: "RED_FP",
      reason: "False positive indicator: " + hardVettingFails.join(", ") + ".",
      decisionReason: "False positive indicator: " + hardVettingFails.join(", ") + ".",
      failed_test: hardVettingFails[0],
      next_action: "exclude",
      suggestedAction: "Candidate excluded from follow-up.",
      signalStatus: "VISIBLE_SIGNAL",
      dataStatus: "TESS_DATA_AVAILABLE",
      monitorStatus: "TESS_DATA_AVAILABLE",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: "false_positive",
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  // Step 7b: Activity/Rotation — soft blocker, not automatically fatal
  if (checks["Activity/Rotation"].status === "failed") {
    if ((signalQuality === "strong" || signalQuality === "medium") && (dataQuality === "high" || dataQuality === "sufficient")) {
      return {
        status: "RECHECK_ACTIVITY",
        reason: "Starker Transit-Kandidat, aber Aktivit\u00e4t/Rotation ist ein kritischer St\u00f6rfaktor.",
        failed_test: "Activity/Rotation",
        next_action: "rotation_activity_check",
        signal_quality: signalQuality,
        data_quality: dataQuality,
        matrix_cell: determineMatrixCell(signalQuality, dataQuality, "RECHECK_ACTIVITY"),
        passed_checks: cats.passed,
        warning_checks: cats.warning,
        failed_checks: cats.failed,
        not_run_checks: cats.notRun,
        blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
        check_tree: checkTree
      };
    }
    return {
      status: "LOW_CONFIDENCE",
      vettingStage2Class: "LOW_CONFIDENCE",
      reason: "Weak signal with rotation/activity risk; likely false positive.",
      decisionReason: "Weak signal with rotation/activity risk; manual review required.",
      failed_test: "Activity/Rotation",
      next_action: "manual_review_required",
      suggestedAction: "Manual review required.",
      signalStatus: "VISIBLE_SIGNAL",
      dataStatus: "TESS_DATA_AVAILABLE",
      monitorStatus: "TESS_DATA_AVAILABLE",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "LOW_CONFIDENCE"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  // Step 8: Check warnings that block EXOFOP
  const blockingWarnings = Object.entries(checks)
    .filter(function(entry) { return entry[1].status === "warning"; })
    .map(function(entry) { return entry[0]; });

  if (blockingWarnings.length > 0) {
    const failedTest = blockingWarnings[0];
    return {
      status: "YELLOW_RECHECK",
      vettingStage2Class: "YELLOW_RECHECK",
      reason: "Follow-up checks incomplete: " + blockingWarnings.join(", ") + ".",
      decisionReason: "Follow-up checks incomplete: " + blockingWarnings.join(", ") + ".",
      failed_test: failedTest,
      next_action: "manual_review_required",
      suggestedAction: "Complete missing vetting checks before ExoFOP submission.",
      signalStatus: "VISIBLE_SIGNAL",
      dataStatus: "TESS_DATA_AVAILABLE",
      monitorStatus: "TESS_DATA_AVAILABLE",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "YELLOW_RECHECK"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
  }

  // Step 9: All checks passed
  return {
    status: "GREEN_SPC",
    vettingStage2Class: "GREEN_SPC",
    reason: "All ExoFOP checks passed.",
    decisionReason: "All ExoFOP checks passed.",
    failed_test: null,
    next_action: "prepare_exofop_upload",
    suggestedAction: "Ready for ExoFOP upload and follow-up prioritization.",
    signalStatus: "VISIBLE_SIGNAL",
    dataStatus: "TESS_DATA_AVAILABLE",
    monitorStatus: "TESS_DATA_AVAILABLE",
    signal_quality: signalQuality,
    data_quality: dataQuality,
    matrix_cell: determineMatrixCell(signalQuality, dataQuality, "EXOFOP_CANDIDATE"),
    passed_checks: cats.passed,
    warning_checks: cats.warning,
    failed_checks: cats.failed,
    not_run_checks: cats.notRun,
    blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
    check_tree: checkTree
  };
}
