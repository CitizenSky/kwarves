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
  if (shape === "V_SHAPE") {
    return { status: "failed", reason: "V-shape transit suggests EB而非 planet" };
  }
  if (shape === "UNKNOWN" || shape === "" || !shape) {
    return { status: "warning", reason: "Transit shape unknown; needs manual review" };
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
  if (["U_SHAPE", "U_SHAPED", "BOX", "BOX_SHAPED", "CLEAR"].includes(shape)) return "CLEAR";
  if (["V_SHAPE", "V_SHAPED"].includes(shape)) return "V_SHAPED";
  if (["NOISE", "NOISY"].includes(shape)) return "NOISY";
  if (["ARTIFACT", "ARTIFACT_LIKE", "SPURIOUS", "INVERTED", "IRREGULAR", "INVALID"].includes(shape)) return "ARTIFACT_LIKE";
  if (depthStability === "UNSTABLE" || depthStability === "HIGH_VARIABILITY") return "ARTIFACT_LIKE";
  return "UNCLEAR";
}

export function evaluateSpcArtStage2(candidate) {
  const visibleTransits = Number(candidate.matrixVisibleTransits ?? candidate.visibleTransits ?? candidate.matrixTransits ?? candidate.transits ?? 0) || 0;
  const expectedTransits = Number(candidate.matrixTransits ?? candidate.transits ?? visibleTransits) || visibleTransits;
  const depthPpt = Number(candidate.depthPpt ?? 0) || 0;
  const durationHours = Number(candidate.durationHours ?? 0) || 0;
  const depthStability = (candidate.depthStability || "").toUpperCase();
  const shapeClass = classifyFoldedLightCurve(candidate);
  const activityRisk = (candidate.rotationRisk || "").toUpperCase();
  const sectorEdgeRisk = (candidate.sectorEdgeRisk || "").toUpperCase();
  const dataGapRisk = (candidate.dataGapRisk || "").toUpperCase();

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
  if (depthStability === "UNKNOWN" || depthStability === "") missingChecks.push("Depth stability measurement");
  if (activityRisk === "UNKNOWN" || activityRisk === "" || activityRisk === "POSSIBLE") missingChecks.push("Activity/Rotation check");
  if (transitStatus.some((item) => item.status !== "OK")) missingChecks.push("Individual transit review");

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
    singleTransitStatus: reproducible ? (stableIndividualTransits ? "STABLE" : "NEEDS_REVIEW") : "NOT_REPRODUCIBLE",
    transits: transitStatus,
    medianDepthPpt: depthPpt || null,
    depthScatterPpt,
    depthStabilityScore,
    depthStability: depthStability || "UNKNOWN",
    foldedLightCurveStatus: shapeClass,
    transitShapeClass: shapeClass,
    activityStatus,
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

  const needsSpcArtStage2 = isSpcArtCandidate(candidate) && !candidate.finalDecision?.spcArtStage2;
  if (candidate.finalDecision && candidate.finalDecision.vettingStage2Class && !needsSpcArtStage2) {
    return candidate.finalDecision;
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
  const spcArtStage2 = isSpcArtCandidate(candidate) ? evaluateSpcArtStage2(candidate) : null;

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
