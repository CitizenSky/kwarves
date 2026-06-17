const HARD_BLOCKING_TTV_STATUSES = new Set([]);
const REVIEW_TTV_STATUSES = new Set([
  "TIMING_OR_DEPTH_SCATTER_RISK",
  "STRONG_TTV",
  "IRREGULAR_TTV",
  "TTV_REVIEW",
  "POSSIBLE_TTV"
]);

function normalize(value) {
  return String(value ?? "").trim().toUpperCase();
}

function numberOrZero(value) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

function unique(items) {
  return [...new Set(items.filter(Boolean))];
}

export function evaluateVvt(candidate) {
  if (!candidate) {
    return {
      vvtScore: 0,
      vvtStatus: "BLOCKED",
      vvtBlockingIssues: ["Missing candidate data"],
      vvtReviewNotes: []
    };
  }

  const text = [
    candidate.status,
    candidate.matrixStatus,
    candidate.matrixClass,
    candidate.reason,
    candidate.decisionReason,
    ...(candidate.displayLabels || [])
  ].join(" ").toUpperCase();
  const evidenceScore = numberOrZero(candidate.evidenceScore);
  const multiMethodScore = numberOrZero(candidate.multiMethodScore ?? candidate.multi_method_score);
  const transitStatus = normalize(candidate.transitEvidenceStatus || candidate.transit_evidence_status);
  const ttvStatus = normalize(candidate.ttvStatus || candidate.ttv_status);
  const blendStatus = normalize(candidate.blendStatus || candidate.blend_status);
  const knownObjectStatus = normalize(candidate.knownObjectStatus || candidate.known_object_status);
  const variabilityStatus = normalize(candidate.variabilityStatus || candidate.variability_status);
  const sectors = numberOrZero(candidate.observedSectorCount ?? candidate.matrixSectors);
  const visibleTransits = numberOrZero(candidate.matrixVisibleTransits ?? candidate.visibleTransits);
  const cleanForExofop = candidate.multiMethodCleanForExofop ?? candidate.multi_method_clean_for_exofop;

  const blockingIssues = [];
  const reviewNotes = [];
  let score = Math.round((evidenceScore * 0.45) + (multiMethodScore * 0.55));

  if (candidate.dataStatus === "NO_TESS_DATA" || candidate.monitorStatus === "NO_TESS_DATA" || sectors <= 0) {
    blockingIssues.push("No TESS/lightcurve data available");
  } else if (sectors < 2 || visibleTransits < 2) {
    blockingIssues.push("WAIT_FOR_DATA: insufficient sector or visible-transit coverage");
  }

  if (!["SUPPORTS", "PARTIAL_SUPPORT"].includes(transitStatus)) {
    blockingIssues.push("Transit evidence is not strong enough for VVT release");
  }
  if (blendStatus && blendStatus !== "NO_LOCAL_BLEND_FLAG") {
    blockingIssues.push("Blend/contamination risk needs resolution");
  }
  if (knownObjectStatus === "KNOWN_FP_OR_EB" || /FALSE_POSITIVE|RED_FP|EB_RISK|REJECTED/.test(text)) {
    blockingIssues.push("Known false-positive or eclipsing-binary risk");
  } else if (knownObjectStatus && knownObjectStatus !== "NO_KNOWN_MATCH") {
    reviewNotes.push("Known-object catalog match needs manual review");
  }
  if (variabilityStatus === "ACTIVITY_OR_VARIABLE_RISK") {
    blockingIssues.push("Activity/variability risk needs resolution");
  } else if (variabilityStatus === "NOT_CHECKED") {
    reviewNotes.push("Variability check is not complete");
  }

  if (HARD_BLOCKING_TTV_STATUSES.has(ttvStatus)) {
    blockingIssues.push(`TTV status ${ttvStatus}`);
  } else if (REVIEW_TTV_STATUSES.has(ttvStatus)) {
    score += 5;
    reviewNotes.push(`${ttvStatus}: manual timing review; not a hard blocker by itself`);
  } else if (ttvStatus === "NOT_ENOUGH_TRANSITS") {
    reviewNotes.push("TTV check waits for more measured individual transits");
  } else if (ttvStatus === "NO_STRONG_TTV_FLAG") {
    reviewNotes.push("No strong TTV flag");
  }

  if (cleanForExofop === true) score += 8;
  if (visibleTransits >= 3) score += 4;
  if (candidate.color === "green") score += 4;
  score = Math.max(0, Math.min(100, Math.round(score)));

  const uniqueBlockers = unique(blockingIssues);
  const uniqueNotes = unique(reviewNotes);
  let status = "NEEDS_REVIEW";
  if (uniqueBlockers.some((item) => item.startsWith("WAIT_FOR_DATA") || item.includes("No TESS"))) {
    status = "WAIT_FOR_DATA";
  } else if (uniqueBlockers.length) {
    status = "BLOCKED";
  } else if (score >= 85 && cleanForExofop === true && !["STRONG_TTV", "IRREGULAR_TTV"].includes(ttvStatus)) {
    status = "EXOFOP_READY";
  }

  return {
    vvtScore: score,
    vvtStatus: status,
    vvtBlockingIssues: uniqueBlockers,
    vvtReviewNotes: uniqueNotes
  };
}
