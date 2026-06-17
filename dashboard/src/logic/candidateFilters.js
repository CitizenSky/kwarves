import { isSpcPrepCandidate, matrixText } from './colorFor.js';
import { isHabitableZoneCandidate } from './habitableZone.js';
import { evaluateVvt } from './vvtScoring.js';

function numberOrZero(value) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

function normalize(value) {
  return String(value ?? "").trim().toUpperCase();
}

function listText(items) {
  return (items || []).map((item) => normalize(item)).join(" ");
}

function hasRejectedLabel(candidate) {
  return /FALSE_POSITIVE|RED_FP|EB_RISK|REJECTED|IGNORE/.test(matrixText(candidate));
}

function candidateFlagText(candidate) {
  return listText([
    candidate?.ttvStatus,
    candidate?.ttv_status,
    candidate?.sciencePriorityStatus,
    candidate?.science_priority_status,
    candidate?.reason,
    candidate?.decisionReason,
    candidate?.nextStep,
    ...(candidate?.candidateFlags || candidate?.candidate_flags || []),
    ...(candidate?.displayLabels || []),
    ...((candidate?.methodEvidenceFlags || candidate?.method_evidence_flags || []).map((flag) => [
      flag?.method,
      flag?.status,
      flag?.effect,
      flag?.reason,
    ].filter(Boolean).join(" "))),
  ]);
}

export function hasRealLightcurve(candidate) {
  return Boolean(candidate?.lightcurveImg || candidate?.lightcurveImgDeploy || candidate?.lightcurveImgLocal);
}

export function hasRealVettingData(candidate) {
  if (candidate?.hasRealVettingData === true) return true;

  const source = normalize(candidate?.realVettingDataSource);
  if (source && !/MISSING|SYNTHETIC|FALLBACK|RUNTIME_FALLBACK|LIMITED_EXPORT/.test(source)) {
    return true;
  }

  const stats = candidate?.individualTransitStatistics || candidate?.individual_transit_statistics || {};
  if (
    normalize(stats.source) === "LEVEL5_SINGLE_TRANSITS" &&
    stats.csvAvailable !== false &&
    numberOrZero(stats.individualTransitCount ?? stats.individual_transit_count) > 0
  ) {
    return true;
  }

  const stage2 = candidate?.spcArtStage2 || {};
  const stage2Source = normalize(stage2.source);
  const stage2Status = normalize(stage2.computationStatus);
  return Boolean(
    stage2Source &&
    !/MISSING|SYNTHETIC|FALLBACK|RUNTIME_FALLBACK|LIMITED_EXPORT/.test(stage2Source) &&
    stage2.fallbackUsed !== true &&
    stage2.stage2Completed !== false &&
    stage2Status !== "NOT_COMPUTED"
  );
}

export function hasHardVvtBlocker(candidate, evaluatedVvt = null) {
  const vvt = evaluatedVvt || (candidate?.vvtStatus ? candidate : evaluateVvt(candidate));
  const blockers = candidate?.vvtBlockingIssues || vvt.vvtBlockingIssues || [];
  return blockers.some((issue) => {
    const text = normalize(issue);
    return text && !/TTV|TIMING|SCATTER/.test(text);
  });
}

export function isVvtBroadReviewCandidate(candidate) {
  const vvt = candidate?.vvtStatus ? candidate : evaluateVvt(candidate);
  const text = matrixText(candidate);
  return (
    ["EXOFOP_READY", "NEEDS_REVIEW"].includes(candidate?.vvtStatus || vvt.vvtStatus) ||
    candidate?.color === "green" ||
    /SPC_STRONG|SPC_FOLLOWUP_READY|SPC_RV_NEEDED/.test(text)
  ) && !hasRejectedLabel(candidate);
}

export function isVvtShortlistCandidate(candidate) {
  const vvt = candidate?.vvtStatus ? candidate : evaluateVvt(candidate);
  const vvtStatus = candidate?.vvtStatus || vvt.vvtStatus;
  const vvtScore = numberOrZero(candidate?.vvtScore ?? vvt.vvtScore);
  const evidenceScore = numberOrZero(candidate?.evidenceScore);
  const text = matrixText(candidate);
  const primarySignal = (
    vvtStatus === "EXOFOP_READY" ||
    (vvtStatus === "NEEDS_REVIEW" && vvtScore >= 70) ||
    (/SPC_STRONG/.test(text) && evidenceScore >= 80)
  );

  return Boolean(
    primarySignal &&
    !hasRejectedLabel(candidate) &&
    !hasHardVvtBlocker(candidate, vvt) &&
    hasRealLightcurve(candidate) &&
    hasRealVettingData(candidate) &&
    !/NO_TESS_DATA|WAIT_FOR_TESS/.test(listText([
      candidate?.status,
      candidate?.matrixStatus,
      candidate?.matrixClass,
      candidate?.dataStatus,
      candidate?.monitorStatus,
    ]))
  );
}

export const isVvtCandidate = isVvtShortlistCandidate;

const TTV_REVIEW_STATUSES = new Set(["POSSIBLE_TTV", "STRONG_TTV", "IRREGULAR_TTV"]);

export function isTtvMultiPlanetReviewCandidate(candidate) {
  const ttvStatus = normalize(candidate?.ttvStatus || candidate?.ttv_status);
  const text = candidateFlagText({
    ...candidate,
    ttvStatus: "",
    ttv_status: "",
  });
  return TTV_REVIEW_STATUSES.has(ttvStatus) || /MULTI_SIGNAL_CANDIDATE|MULTI_PLANET_CANDIDATE/.test(text);
}

export function candidateMatchesColorFilter(candidate, colorFilter = 'all') {
  switch (colorFilter) {
    case 'all':
      return true;
    case 'violet':
      return isHabitableZoneCandidate(candidate);
    case 'spc-prep':
      return isSpcPrepCandidate(candidate);
    case 'vvt':
      return isVvtShortlistCandidate(candidate);
    case 'ttv':
      return isTtvMultiPlanetReviewCandidate(candidate);
    case 'yellow':
      return candidate?.color === 'yellow' && !isSpcPrepCandidate(candidate);
    case 'green':
    case 'red':
    case 'gray':
      return candidate?.color === colorFilter;
    default:
      return false;
  }
}
