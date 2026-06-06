import { t } from '../i18n.js';
import { state } from '../state.js';
import { data } from '../dataLoader.js';
import { matrixText, localizedBaseColorLabel, isSpcStrong, isSpcPrepCandidate, isSpcArt, isSpc, isRvNeeded } from '../logic/colorFor.js';
import { candidateLabel } from '../logic/candidateLabel.js';

function matchesCandidate(candidate, term) {
  if (!term) return true;
  return [
    candidate.tic,
    candidate.status,
    candidate.matrixStatus,
    candidate.matrixClass,
    candidate.decisionReason,
    candidate.nextStep,
    candidate.reason,
    candidate.hz,
    candidate.baseColorLabel,
    localizedBaseColorLabel(candidate),
    candidate.isViolet ? `${t("filter_violet")} violet violett` : ""
  ].join(" ").toLowerCase().includes(term);
}

function publicCandidatePool() {
  return (data.candidates || []).filter((candidate) => (
    candidate.color === "green" ||
    isSpcPrepCandidate(candidate) ||
    (
      candidate.color === "yellow" &&
      candidate.followupStrength === "STRONG" &&
      /HIGH_VALUE_HZ_RECHECK|FOLLOWUP_PRIORITY/.test(matrixText(candidate)) &&
      !/EB_RISK|REJECTED|IGNORE/.test(matrixText(candidate))
    )
  ));
}

export function matrixStatusBucket(candidate) {
  const text = matrixText(candidate);
  if (text.includes("EB_RISK")) return "EB_RISK";
  if (String(candidate.matrixStatus || "").toUpperCase() === "IGNORE") return "IGNORE";
  if (isSpcStrong(candidate)) return "SPC_STRONG";
  if (isSpcPrepCandidate(candidate)) return "SPC_FOLLOWUP_READY";
  if (isSpcArt(candidate)) return "SPC_ART";
  if (text.includes("NEEDS_MORE")) return "NEEDS_MORE_DATA";
  if (text.includes("REJECT") || text.includes("FALSE") || text.includes(" FP") || text.includes("ARTIFACT")) return "REJECTED";
  if (isSpc(candidate)) return "SPC";
  return "IGNORE";
}

export function countWhere(items, predicate) {
  return items.reduce((sum, item) => sum + (predicate(item) ? 1 : 0), 0);
}

export function countBuckets(items, labels, picker) {
  const counts = Object.fromEntries(labels.map((label) => [label, 0]));
  items.forEach((item) => {
    const key = picker(item);
    if (Object.prototype.hasOwnProperty.call(counts, key)) counts[key] += 1;
  });
  return labels.map((label) => ({ label, count: counts[label] || 0 }));
}

export function expectedTransits(candidate) {
  return Number(candidate.matrixTransits ?? candidate.transits ?? 0) || 0;
}

export function visibleMatrixTransits(candidate) {
  return Number(candidate.matrixVisibleTransits ?? candidate.visibleTransits ?? 0) || 0;
}

export function coveragePercent(candidate) {
  const expected = expectedTransits(candidate);
  if (!expected) return 0;
  return Math.round((visibleMatrixTransits(candidate) / expected) * 100);
}

export function hzPriority(candidate) {
  return candidate.isViolet ? 0 : (candidate.hz && candidate.hz !== "ZU_HEISS" ? 1 : 2);
}

export function statusPriority(candidate) {
  const label = `${candidate.matrixClass} ${candidate.matrixStatus} ${candidate.status}`.toUpperCase();
  if (label.includes("SPC_RV_NEEDED") || label.includes("SPC_STRONG")) return 0;
  if (label.includes("SPC_FOLLOWUP_READY") || label.includes("SPC")) return 1;
  if (label.includes("NEEDS_MORE")) return 2;
  return 3;
}

export function followupShortLabel(candidate) {
  const text = matrixText(candidate);
  if (text.includes("FOLLOWUP_PRIORITY")) return "PRIORITY";
  if (text.includes("SPC_ACTIVE_STAR")) return "ACTIVE_STAR";
  if (text.includes("SPC_FOLLOWUP_READY")) return "SPC_READY";
  if (text.includes("RV_NEEDED")) return "RV_NEEDED";
  return shortText(candidateLabel(candidate).replace(/^SPC_/, ""), 12);
}

export function candidateNotes(candidate) {
  if (candidate.color !== "green" && expectedTransits(candidate) < 5) return "Recheck: weniger als 5 Transits";
  if (candidate.nextStep) return candidate.nextStep;
  if (candidate.decisionReason) return candidate.decisionReason;
  return candidate.reason || "-";
}

export function shortText(text, maxLength = 86) {
  const value = String(text || "-").trim();
  return value.length > maxLength ? `${value.slice(0, maxLength - 1).trim()}...` : value;
}

export function followupRank(candidate) {
  if (candidate.followupStrength === "STRONG") return 0;
  if (isSpcPrepCandidate(candidate)) return 1;
  if (candidate.color === "green") return 1;
  if (candidate.followupStrength === "MEDIUM") return 2;
  return 3;
}

export function exofopReadiness(candidate) {
  const text = matrixText(candidate);
  if (candidate.color === "green" && /SPC|RV_NEEDED|FOLLOWUP/.test(text)) return "READY_FOR_EXOFOP";
  return "NOT_READY";
}

export function exofopCriteriaFulfilled(candidate) {
  return exofopReadiness(candidate) === "READY_FOR_EXOFOP";
}

export function exofopUploadCandidates(term = "") {
  const normalizedTerm = String(term || "").trim().toLowerCase();
  return [...(data.candidates || [])]
    .filter((candidate) => exofopReadiness(candidate) === "READY_FOR_EXOFOP")
    .filter((candidate) => matchesCandidate(candidate, normalizedTerm))
    .sort((a, b) => (
      (Number(b.evidenceScore || 0) - Number(a.evidenceScore || 0))
      || (Number(b.matrixVisibleTransits || 0) - Number(a.matrixVisibleTransits || 0))
      || (Number(a.distance || 0) - Number(b.distance || 0))
    ))
    .slice(0, 40);
}

export function top20Candidates() {
  return [...publicCandidatePool()]
    .sort((a, b) => (
      (followupRank(a) - followupRank(b))
      || (Number(b.evidenceScore || 0) - Number(a.evidenceScore || 0))
      || (hzPriority(a) - hzPriority(b))
      || (statusPriority(a) - statusPriority(b))
      || (Number(a.distance || 0) - Number(b.distance || 0))
    ))
    .slice(0, 20);
}

export function followupCandidates() {
  return [...(data.candidates || [])]
    .filter((candidate) => (
      isSpcPrepCandidate(candidate) ||
      isRvNeeded(candidate) ||
      isSpcStrong(candidate) ||
      (
        candidate.followupStrength === "STRONG" &&
        /FOLLOWUP|HIGH_VALUE_HZ_RECHECK|SPC/.test(matrixText(candidate)) &&
        !/EB_RISK|REJECTED|IGNORE/.test(matrixText(candidate))
      )
    ))
    .sort((a, b) => (
      (followupRank(a) - followupRank(b))
      || (Number(b.evidenceScore || 0) - Number(a.evidenceScore || 0))
      || (hzPriority(a) - hzPriority(b))
      || (Number(a.distance || 0) - Number(b.distance || 0))
    ));
}

export function numericBucket(value, buckets) {
  const number = Number(value || 0);
  return buckets.find((bucket) => number >= bucket.min && number < bucket.max)?.label || buckets[buckets.length - 1].label;
}

export function chartRows(labels, picker) {
  return countBuckets(data.candidates || [], labels, picker);
}
