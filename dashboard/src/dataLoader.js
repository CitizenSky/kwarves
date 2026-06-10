import { state, tessYear8SectorSet } from './state.js';
import { t, normalizeSectorList, formatDateRange, daysDiff, formatDate, formatNumber, formatSectorList } from './i18n.js';
import { isSpcPrepCandidate, matrixText, localizedBaseColorLabel } from './logic/colorFor.js';

export const DASHBOARD_UI_VERSION = "2026-06-02-r";

export const data = { summary: {}, tree: [], candidates: [], lightcurveCandidates: [], priorityCandidates: [] };
export const notifications = window.ASTRO_DASHBOARD_NOTIFICATIONS || { generatedAt: "", total: 0, counts: {}, items: [] };

const detailCache = new Map();
let fallbackLoadPromise = null;

function applyDashboardPayload(payload, source = "unknown") {
  if (!payload || !Array.isArray(payload.candidates)) return false;
  data.generatedAt = payload.generatedAt || "";
  data.summary = payload.summary || {};
  data.tess = payload.tess || {};
  data.tree = payload.tree || [];
  data.candidates = payload.candidates || [];
  data.lightcurveCandidates = payload.lightcurveCandidates || data.candidates.filter((candidate) => candidate.lightcurveImg);
  data.priorityCandidates = payload.priorityCandidates || data.lightcurveCandidates;
  data.splitDataVersion = payload.splitDataVersion || null;
  data.detailsPattern = payload.detailsPattern || "";
  window.ASTRO_DASHBOARD_DATA = data;
  console.log("[kwarves] Data loaded from", source + ":", data.candidates.length, "candidates");
  console.log("[kwarves] Summary:", JSON.stringify(data.summary));
  return data.candidates.length > 0;
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return response.json();
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", reject, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

async function loadDashboardDataFallback() {
  if (!fallbackLoadPromise) {
    fallbackLoadPromise = (async () => {
      await loadScript("dashboard-data.js");
      if (!window.ASTRO_DASHBOARD_DATA) throw new Error("dashboard-data.js loaded without ASTRO_DASHBOARD_DATA");
      applyDashboardPayload(window.ASTRO_DASHBOARD_DATA, "dashboard-data.js fallback");
      return window.ASTRO_DASHBOARD_DATA;
    })();
  }
  return fallbackLoadPromise;
}

export function loadData() {
  const statusEl = document.getElementById("dataStatus");
  if (statusEl) statusEl.textContent = "Lade Kandidaten-Summary...";
  return fetchJson("candidates-summary.json")
    .then((payload) => applyDashboardPayload(payload, "candidates-summary.json"))
    .catch((error) => {
      console.warn("[kwarves] candidates-summary.json unavailable, using dashboard-data.js fallback.", error);
      if (statusEl) statusEl.textContent = "Summary nicht verfügbar, lade Fallback...";
      return loadDashboardDataFallback().then(() => data.candidates.length > 0);
    })
    .then((ok) => {
      const count = data.candidates?.length || 0;
      if (statusEl) {
        if (ok && count > 0) {
          statusEl.textContent = "Daten geladen: " + count + " Kandidaten";
          statusEl.style.background = "#00b894";
          statusEl.style.color = "#fff";
          setTimeout(() => { statusEl.style.opacity = "0"; setTimeout(() => statusEl.remove(), 500); }, 3000);
        } else {
          statusEl.textContent = "Datenfehler: 0 Kandidaten geladen";
          statusEl.style.background = "#ff4444";
          statusEl.style.color = "#fff";
        }
      }
      return ok && count > 0;
    });
}

export async function loadCandidateDetails(candidateOrTic) {
  const tic = Number(typeof candidateOrTic === "object" ? candidateOrTic?.tic : candidateOrTic);
  if (!Number.isFinite(tic)) return null;
  const existing = data.candidates.find((candidate) => candidate.tic === tic) || null;
  if (existing?._detailLoaded) return existing;
  if (detailCache.has(tic)) return detailCache.get(tic);

  const detailPromise = (async () => {
    try {
      const detailsPath = existing?.detailsPath || `candidate-details/TIC_${tic}.json`;
      const detail = await fetchJson(detailsPath);
      const target = existing || detail;
      Object.assign(target, detail, { _detailLoaded: true });
      return target;
    } catch (error) {
      console.warn(`[kwarves] detail load failed for TIC ${tic}; using dashboard-data.js fallback.`, error);
      const fallback = await loadDashboardDataFallback();
      const detail = fallback.candidates?.find((candidate) => candidate.tic === tic) || existing;
      if (detail && existing && detail !== existing) Object.assign(existing, detail, { _detailLoaded: true });
      else if (detail) detail._detailLoaded = true;
      return existing || detail || null;
    }
  })();
  detailCache.set(tic, detailPromise);
  return detailPromise;
}

export const els = {
  globalSearch: document.getElementById("globalSearch"),
  curveSearch: document.getElementById("curveSearch"),
  tree: document.getElementById("tree"),
  visitorKpis: document.getElementById("visitorKpis"),
  labelLegendRows: document.getElementById("labelLegendRows"),
  topCandidateRows: document.getElementById("topCandidateRows"),
  topCandidatesRow: document.getElementById("topCandidatesRow"),
  topCandidatesCount: document.getElementById("topCandidatesCount"),
  followupCandidateRows: document.getElementById("followupCandidateRows"),
  followupCandidateCount: document.getElementById("followupCandidateCount"),
  vvtCandidateRows: document.getElementById("vvtCandidateRows"),
  vvtCandidateCount: document.getElementById("vvtCandidateCount"),
  toggleFollowupList: document.getElementById("toggleFollowupList"),
  visitorTimeline: document.getElementById("visitorTimeline"),
  yellowSelectedReason: document.getElementById("yellowSelectedReason"),
  matrixStats: document.getElementById("matrixStats"),
  selectedCard: document.getElementById("selectedCard"),
  selectedCardSection: document.getElementById("selectedCardSection"),
  selectedCardTitle: document.getElementById("selectedCardTitle"),
  selectedCardTic: document.getElementById("selectedCardTic"),
  toggleSelectedCard: document.getElementById("toggleSelectedCard"),
  rows: document.getElementById("candidateRows"),
  docsFlow: document.getElementById("docsFlow"),
  docsLevels: document.getElementById("docsLevels"),
  docsScriptRows: document.getElementById("docsScriptRows"),
  curveList: document.getElementById("curveList"),
  curveTitle: document.getElementById("curveTitle"),
  curveMeta: document.getElementById("curveMeta"),
  curveImageWrap: document.getElementById("curveImageWrap"),
  mapCanvas: document.getElementById("starMap2d"),
  mapFrame: document.getElementById("mapFrame"),
  map3d: document.getElementById("map3d"),
  mapZoomValue: document.getElementById("mapZoomValue"),
  mapSelectedTic: document.getElementById("mapSelectedTic"),
  mapObservedSectors: document.getElementById("mapObservedSectors"),
  mapNextRecheck: document.getElementById("mapNextRecheck"),
  mapCoverageStatus: document.getElementById("mapCoverageStatus"),
  tessCompareCard: document.getElementById("tessCompareCard"),
  tessCompareToggle: document.getElementById("tessCompareToggle"),
  tessSectorCanvas: document.getElementById("tessSector2d"),
  tessSectorFrame: document.getElementById("tessSectorFrame"),
  tessSector3d: document.getElementById("tessSector3d"),
  tessMatchSelectedTic: document.getElementById("tessMatchSelectedTic"),
  tessMatchSectorList: document.getElementById("tessMatchSectorList"),
  tessMatchYear8Overlap: document.getElementById("tessMatchYear8Overlap"),
  tessMatchCurrent: document.getElementById("tessMatchCurrent"),
  tessMatchCoverage: document.getElementById("tessMatchCoverage"),
  tessTimelineObserved: document.getElementById("tessTimelineObserved"),
  tessTimelinePlanned: document.getElementById("tessTimelinePlanned"),
  tessTimelineNext: document.getElementById("tessTimelineNext"),
  tessTimelineStatus: document.getElementById("tessTimelineStatus"),
  notificationBadge: document.getElementById("notificationBadge"),
  notificationPanel: document.getElementById("notificationPanel"),
  notificationTitle: document.getElementById("notificationTitle"),
  notificationSummary: document.getElementById("notificationSummary"),
  notificationList: document.getElementById("notificationList"),
  toast: document.getElementById("toast"),
  tessCurrentSector: document.getElementById("tessCurrentSector"),
  tessCurrentWindow: document.getElementById("tessCurrentWindow"),
  tessTotalNumbered: document.getElementById("tessTotalNumbered"),
  tessPrimaryCount: document.getElementById("tessPrimaryCount"),
  tessCurrentStatus: document.getElementById("tessCurrentStatus"),
  tessYear8Info: document.getElementById("tessYear8Info"),
  tessGeometryInfo: document.getElementById("tessGeometryInfo"),
  tessScheduleRows: document.getElementById("tessScheduleRows"),
  tessUpdatedAt: document.getElementById("tessUpdatedAt"),
  adminLoginCard: document.getElementById("adminLoginCard"),
  adminLoginForm: document.getElementById("adminLoginForm"),
  adminUserInput: document.getElementById("adminUserInput"),
  adminPassInput: document.getElementById("adminPassInput"),
  adminLoginHint: document.getElementById("adminLoginHint"),
  adminStatsWrap: document.getElementById("adminStatsWrap"),
  adminViews: document.getElementById("adminViews"),
  adminSessions: document.getElementById("adminSessions"),
  adminAvgDuration: document.getElementById("adminAvgDuration"),
  adminLastVisit: document.getElementById("adminLastVisit"),
  adminCurrentCountry: document.getElementById("adminCurrentCountry"),
  adminCountrySource: document.getElementById("adminCountrySource"),
  adminCountryRows: document.getElementById("adminCountryRows"),
  adminGlobalStatus: document.getElementById("adminGlobalStatus"),
  adminGlobalDetails: document.getElementById("adminGlobalDetails"),
  adminGlobalDashboardLink: document.getElementById("adminGlobalDashboardLink"),
  adminSelfFilterStatus: document.getElementById("adminSelfFilterStatus"),
  adminToggleSelfFilter: document.getElementById("adminToggleSelfFilter"),
  adminToggleSelfFilterLabel: document.getElementById("adminToggleSelfFilterLabel"),
  adminGoatTitle: document.getElementById("adminGoatTitle"),
  adminGoatText: document.getElementById("adminGoatText"),
  adminGoatButton: document.getElementById("adminGoatButton"),
  adminGoatButtonLabel: document.getElementById("adminGoatButtonLabel"),
  adminLocalTitle: document.getElementById("adminLocalTitle"),
  adminLocalText: document.getElementById("adminLocalText"),
  adminExofopRows: document.getElementById("adminExofopRows")
};

export let points2d = [];
export let three = {};
export let tessPoints2d = [];
export let tessThree = { ready: false };
export let visitorCharts = [];

export function selectedCandidateSectorInfo() {
  const candidate = state.selected || null;
  const sectors = normalizeSectorList(candidate && candidate.observedSectors);
  return {
    candidate,
    sectors,
    plannedSectors: normalizeSectorList(candidate && candidate.plannedSectors),
    sectorSet: new Set(sectors)
  };
}

export function selectedMapFocus(candidates = data.candidates || []) {
  if (!state.selected) return null;
  return candidates.find((candidate) => candidate.tic === state.selected.tic) || null;
}

export function buildCandidateCoverageModel(scheduleState) {
  const info = selectedCandidateSectorInfo();
  const candidate = info.candidate;
  const observed = info.sectors;
  const observedSet = new Set(observed);
  const plannedIds = new Set(info.plannedSectors);
  const planned = scheduleState.schedule.filter((item) => plannedIds.has(item.sector));
  const hasFutureKnownSectors = scheduleState.schedule.some((item) => item.phase !== "completed");

  const nextItem = planned.find((item) => item.phase !== "completed") || planned[planned.length - 1] || null;
  const overlapYear8 = observed.filter((sector) => tessYear8SectorSet.has(sector));
  const inPlannedArea = ["LIVE_NOW", "UPCOMING"].includes(candidate?.recheckStatus || "");

  let nextObservationText = t("next_no_sector");
  if (nextItem) {
    if (nextItem.phase === "running") {
      nextObservationText = t("next_running", {
        sector: nextItem.sector,
        range: formatDateRange(nextItem.start, nextItem.end)
      });
    } else {
      const startsIn = Math.max(0, daysDiff(scheduleState.now, nextItem.startDate));
      nextObservationText = t("next_in_days", {
        sector: nextItem.sector,
        days: startsIn,
        date: formatDate(nextItem.start)
      });
    }
  }

  let statusText = t("no_candidate_selected");
  let statusKey = "neutral";
  if (candidate) {
    if (candidate.recheckStatus === "LIVE_NOW") {
      statusText = `LIVE_NOW \u00b7 ${t("status_recheck_possible")}`;
      statusKey = "green";
    } else if (candidate.recheckStatus === "UPCOMING") {
      statusText = `UPCOMING \u00b7 ${t("status_recheck_possible")}`;
      statusKey = "blue";
    } else if (candidate.recheckStatus === "WAITING_DATA") {
      statusText = `WAITING_DATA \u00b7 ${t("status_waiting_data")}`;
      statusKey = "yellow";
    } else if (!observed.length) {
      statusText = t("status_add_sector_data");
      statusKey = "missing";
    } else {
      statusText = `NO_PLANNED_RECHECK \u00b7 ${t("status_no_recheck")}`;
      statusKey = "gray";
    }
  }

  return {
    candidate,
    observed,
    overlapYear8,
    planned,
    nextItem,
    inPlannedArea,
    hasFutureKnownSectors,
    nextObservationText,
    statusText,
    statusKey,
    estimatedDataAvailable: candidate?.estimatedDataAvailable || ""
  };
}

export function matchesCandidate(candidate, term) {
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

export function publicVisibleCandidates() {
  return data.candidates || [];
}

export function filteredCandidates() {
  const term = els.globalSearch.value.trim().toLowerCase();
  return publicVisibleCandidates().filter((candidate) => {
    const matchesColor =
      state.colorFilter === "all" ||
      (state.colorFilter === "violet"
        ? candidate.isViolet
        : state.colorFilter === "spc-prep"
          ? isSpcPrepCandidate(candidate)
          : state.colorFilter === "yellow"
            ? candidate.color === "yellow" && !isSpcPrepCandidate(candidate)
            : candidate.color === state.colorFilter);
    return matchesColor && matchesCandidate(candidate, term);
  });
}

export function publicCandidatePool() {
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

export function publicMatrixCandidates() {
  const term = els.globalSearch.value.trim().toLowerCase();
  return publicVisibleCandidates().filter((candidate) => matchesCandidate(candidate, term));
}

export { matrixText, colorClass, candidateVisualClass, candidateMapColor, candidateGroupLabel, matrixColorClass, localizedBaseColorLabel, colorName, mapSourceLabel, currentMapNoticeText, isSpcArt, isRvNeeded, isSpcStrong, isSpc, isSpcPrepCandidate } from './logic/colorFor.js';
export { matrixStatusBucket, countWhere, countBuckets, expectedTransits, visibleMatrixTransits, coveragePercent, hzPriority, statusPriority, followupShortLabel, candidateNotes, shortText, followupRank, exofopReadiness, exofopCriteriaFulfilled, exofopUploadCandidates, top20Candidates, followupCandidates, vvtQueueCandidates, numericBucket, chartRows } from './logic/candidateScoring.js';
export { reasonTagList, nextCheckList, candidateChip } from './logic/yellowReasonTags.js';
export { candidateLabel, recheckChip } from './logic/candidateLabel.js';
export { renderStatRows, notificationSeverityClass, formatNotificationValue } from './logic/renderHelpers.js';
export { formatNumber, formatDate, formatSectorList } from './i18n.js';
