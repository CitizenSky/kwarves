// Thresholds match config/pipeline_thresholds.json
export const MIN_SECTORS_FOR_DATA = 2;
export const MIN_TRANSITS_FOR_DATA = 3;
export const STRONG_SCORE = 65;
export const MEDIUM_SCORE = 40;
export const HIGH_SECTORS = 8;
export const HIGH_TRANSITS = 3;
export const SIGNAL_MIN_SCORE = 20;

export function checkTessData(candidate) {
  const sectors = candidate.observedSectorCount || 0;
  if (sectors <= 0) {
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

  const checks = runAllChecks(candidate);
  const cats = categorizeChecks(checks);
  const signalQuality = computeSignalQuality(candidate);
  const dataQuality = computeDataQuality(candidate);

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
      status: "NO_PLANET",
      reason: "No BLS/TLS signal detected.",
      failed_test: "Signal Detection",
      next_action: "exclude",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "NO_PLANET"),
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
      status: "NO_PLANET",
      reason: "Folded light curve indicates EB or artifact.",
      failed_test: "Folded Light Curve",
      next_action: "exclude",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "NO_PLANET"),
      passed_checks: cats.passed,
      warning_checks: cats.warning,
      failed_checks: cats.failed,
      not_run_checks: cats.notRun,
      blockers: cats.blockers.map(function(b) { return b.check + ": " + b.reason; }),
      check_tree: checkTree
    };
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
      status: "NO_PLANET",
      reason: "False positive indicator: " + hardVettingFails.join(", ") + ".",
      failed_test: hardVettingFails[0],
      next_action: "exclude",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "NO_PLANET"),
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
      status: "NO_PLANET",
      reason: "Weak signal with rotation/activity risk; likely false positive.",
      failed_test: "Activity/Rotation",
      next_action: "exclude",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "NO_PLANET"),
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
      status: "NO_PLANET",
      reason: "Follow-up checks incomplete: " + blockingWarnings.join(", ") + ".",
      failed_test: failedTest,
      next_action: "manual_review_required",
      signal_quality: signalQuality,
      data_quality: dataQuality,
      matrix_cell: determineMatrixCell(signalQuality, dataQuality, "NO_PLANET"),
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
    status: "EXOFOP_CANDIDATE",
    reason: "All ExoFOP checks passed.",
    failed_test: null,
    next_action: "prepare_exofop_upload",
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
