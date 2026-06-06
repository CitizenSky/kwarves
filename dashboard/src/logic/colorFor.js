import { colors } from '../state.js';
import { t, formatNumber, formatFloat } from '../i18n.js';

export function matrixText(candidate) {
  return [
    candidate.status,
    candidate.matrixStatus,
    candidate.matrixClass,
    candidate.matrixScoreBand,
    ...(candidate.displayLabels || []),
    candidate.decisionReason,
    candidate.nextStep,
    candidate.notes,
    candidate.markierungsKlasse,
    candidate.transitShape,
    candidate.sapPdcsapMatch,
    candidate.oddEvenResult,
    candidate.secondaryEclipse,
    candidate.rotationRisk,
    candidate.dataGapRisk,
    candidate.sectorEdgeRisk
  ].join(" ").toUpperCase();
}

export function isSpcArt(candidate) {
  return matrixText(candidate).includes("SPC_ART");
}

export function isRvNeeded(candidate) {
  return matrixText(candidate).includes("RV_NEEDED");
}

export function isSpcStrong(candidate) {
  const text = matrixText(candidate);
  return text.includes("SPC_STRONG") || text.includes("BAYES_STRONG") || (isRvNeeded(candidate) && Number(candidate.evidenceScore || 0) >= 80);
}

export function isSpc(candidate) {
  const text = matrixText(candidate);
  return isSpcStrong(candidate) || isRvNeeded(candidate) || text.includes("SPC_FOLLOWUP_READY") || candidate.color === "green";
}

export function isSpcPrepCandidate(candidate) {
  const text = matrixText(candidate);
  return candidate.color === "yellow" && text.includes("SPC_FOLLOWUP_READY");
}

export function matrixColorClass(candidate) {
  const raw = String(candidate.matrixColor || "").toLowerCase();
  if (raw === "green") return "green";
  if (raw === "yellow") return "yellow";
  if (raw === "red") return "red";
  if (raw === "purple" || raw === "violet") return "violet";
  if (raw === "gray" || raw === "grey") return "gray";
  return "gray";
}

export function localizedBaseColorLabel(candidate) {
  const explicit = String(candidate.color || "").toLowerCase();
  const raw = String(candidate.baseColorLabel || "").toLowerCase();
  if (explicit === "green" || raw.includes("gruen") || raw.includes("green") || raw.includes("vert")) return t("filter_green");
  if (explicit === "yellow" || raw.includes("gelb") || raw.includes("yellow") || raw.includes("jaune") || raw.includes("orange")) return t("filter_yellow");
  if (explicit === "red" || raw.includes("rot") || raw.includes("red") || raw.includes("rouge")) return t("filter_red");
  if (candidate.isViolet || raw.includes("violett") || raw.includes("violet")) return t("filter_violet");
  return candidate.baseColorLabel || "-";
}

export function colorName(candidate) {
  const baseLabel = localizedBaseColorLabel(candidate);
  if (candidate.isViolet && String(baseLabel).toLowerCase() !== String(t("filter_green")).toLowerCase()) {
    return t("color_plus_violet", { base: baseLabel });
  }
  if (candidate.isViolet) return t("color_green_violet");
  return baseLabel;
}

export function colorClass(candidate) {
  if (isSpcPrepCandidate(candidate)) return "spc-prep";
  if (candidate.isViolet) return "violet";
  return candidate.color;
}

export function candidateVisualClass(candidate) {
  if (isSpcPrepCandidate(candidate)) return "spc-prep";
  return matrixColorClass(candidate);
}

export function candidateMapColor(candidate) {
  return isSpcPrepCandidate(candidate) ? colors.spcPrep : (colors[candidate.color] || colors.gray);
}

export function candidateGroupLabel(candidate) {
  if (isSpcPrepCandidate(candidate)) return "SPC Prep (gelb)";
  return colorName(candidate);
}

export function mapSourceLabel(candidate) {
  const source = String(candidate?.mapSource || "").toLowerCase();
  if (source === "gaia_dr3") return t("map_source_gaia");
  return t("map_source_fallback");
}

export function currentMapNoticeText() {
  const data = window.ASTRO_DASHBOARD_DATA || {};
  const summary = data.summary || {};
  const mode = String(summary.mapMode || "");
  if (mode === "gaia_full") {
    return t("map_notice_gaia_full", {
      total: formatNumber(summary.total || data.candidates.length || 0),
    });
  }
  if (mode === "gaia_mixed") {
    return t("map_notice_gaia_mixed", {
      gaia: formatNumber(summary.mapAstrometric || 0),
      fallback: formatNumber(summary.mapFallback || 0),
      pct: formatFloat(summary.mapCoveragePct, 2, "0"),
    });
  }
  return t("map_notice_symbolic");
}
