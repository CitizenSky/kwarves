import { state } from '../state.js';
import { t, formatNumber, formatMaybe, formatFloat, formatSectorList, formatDate, formatMonthYear, labelLegend, labelLegendLocalized } from '../i18n.js';
import { els, data, countWhere, expectedTransits, countBuckets, matrixText, isSpcArt, isSpcPrepCandidate, isSpc, isSpcStrong, isRvNeeded, matrixStatusBucket, visibleMatrixTransits, coveragePercent } from '../dataLoader.js';
import { publicCandidatePool, publicVisibleCandidates } from './candidateList.js';
import { candidateChip } from './candidateCard.js';

export function renderStatRows(rows, maxValue) {
  const max = Math.max(1, maxValue ?? Math.max(...rows.map((row) => row.count), 1));
  return rows.map((row) => `
    <div class="matrix-stat-row">
      <span>${row.label}</span>
      <strong>${formatNumber(row.count)}</strong>
      <span class="matrix-bar"><span style="width:${Math.min(100, (row.count / max) * 100)}%"></span></span>
    </div>
  `).join("");
}

export function renderVisitorTimeline() {
  const candidates = publicVisibleCandidates();
  const observed = countWhere(candidates, (c) => Number(c.observedSectorCount || 0) > 0 || Number(c.matrixSectors || 0) > 0);
  const year8 = countWhere(candidates, (c) => (c.plannedSectors || []).length > 0);
  const newSectors = countWhere(candidates, (c) => Number(c.newSectors?.length || 0) > 0);
  const timelineCopy = {
    de: [
      ["Vorhandene Sektoren", observed, "Kandidaten mit Sektor-/Matrixdaten"],
      ["LIVE_NOW", countWhere(candidates, (c) => c.recheckStatus === "LIVE_NOW"), "aktueller laufender Sektor"],
      ["UPCOMING", countWhere(candidates, (c) => c.recheckStatus === "UPCOMING"), "kommende Beobachtung geplant"],
      ["WAITING_DATA", countWhere(candidates, (c) => c.recheckStatus === "WAITING_DATA"), "Datenveroeffentlichung abwarten"],
      ["Year-8-Treffer", year8, "geometrische Recheck-Hinweise"],
      ["Neue Sektoren", newSectors, "spaeter fuer Rechecks nutzbar"]
    ],
    en: [
      ["Existing sectors", observed, "candidates with sector/matrix data"],
      ["LIVE_NOW", countWhere(candidates, (c) => c.recheckStatus === "LIVE_NOW"), "current running sector"],
      ["UPCOMING", countWhere(candidates, (c) => c.recheckStatus === "UPCOMING"), "upcoming observation planned"],
      ["WAITING_DATA", countWhere(candidates, (c) => c.recheckStatus === "WAITING_DATA"), "waiting for data release"],
      ["Year-8 hits", year8, "geometric recheck hints"],
      ["New sectors", newSectors, "usable for later rechecks"]
    ],
    fr: [
      ["Secteurs existants", observed, "candidats avec donnees secteur/matrice"],
      ["LIVE_NOW", countWhere(candidates, (c) => c.recheckStatus === "LIVE_NOW"), "secteur actuellement en cours"],
      ["UPCOMING", countWhere(candidates, (c) => c.recheckStatus === "UPCOMING"), "observation a venir planifiee"],
      ["WAITING_DATA", countWhere(candidates, (c) => c.recheckStatus === "WAITING_DATA"), "attente publication donnees"],
      ["Hits Year-8", year8, "indices geometriques de recheck"],
      ["Nouveaux secteurs", newSectors, "utilisables pour rechecks ulterieurs"]
    ]
  };
  const cards = timelineCopy[state.lang] || timelineCopy.de;
  els.visitorTimeline.innerHTML = cards.map(([label, value, note]) => `
    <article class="timeline-card"><span>${label}</span><strong>${formatNumber(value)}</strong><p class="mini">${note}</p></article>
  `).join("");
}

export function renderLabelLegend() {
  const meanings = labelLegendLocalized[state.lang] || labelLegendLocalized.de;
  els.labelLegendRows.innerHTML = labelLegend.map(([label, meaning]) => `
    <tr><td><strong>${label}</strong></td><td>${meanings[label] || meaning}</td></tr>
  `).join("");
}

export function renderMatrixStats() {
  const candidates = publicCandidatePool();
  const copy = {
    de: {
      kpis: {
        total_scanned: "gesamt gescannt",
        total_candidates: "Kandidaten gesamt",
        total_spc: "SPC",
        total_spc_strong: "starke SPC",
        total_spc_prep_yellow: "SPC Prep gelb",
        total_hz: "HZ gesamt",
        total_rv_needed: "RV benoetigt",
        total_rejected: "abgelehnt",
        total_needs_more_data: "mehr Daten noetig"
      },
      pipeline: "Pipeline-Funnel",
      status: "Status-Verteilung",
      hz: "HZ-Statistik",
      falsePositive: "False-Positive-Gruende",
      distance: "Entfernungsklassen",
      radius: "Planetengroessen",
      top: "Top Kandidaten",
      tess: "TESS-Abdeckung",
      distanceColumn: "Distanz",
      noHits: "Keine Treffer",
      spcArtHigh: "SPC_ART hoher Score"
    },
    en: {
      kpis: {
        total_scanned: "total scanned",
        total_candidates: "total candidates",
        total_spc: "SPC",
        total_spc_strong: "strong SPC",
        total_spc_prep_yellow: "yellow SPC prep",
        total_hz: "HZ total",
        total_rv_needed: "RV needed",
        total_rejected: "rejected",
        total_needs_more_data: "needs more data"
      },
      pipeline: "Pipeline funnel",
      status: "Status distribution",
      hz: "HZ statistics",
      falsePositive: "False-positive reasons",
      distance: "Distance classes",
      radius: "Planet sizes",
      top: "Top candidates",
      tess: "TESS coverage",
      distanceColumn: "Distance",
      noHits: "No matches",
      spcArtHigh: "High-score SPC_ART"
    },
    fr: {
      kpis: {
        total_scanned: "total analyse",
        total_candidates: "candidats au total",
        total_spc: "SPC",
        total_spc_strong: "SPC forts",
        total_spc_prep_yellow: "SPC prep jaune",
        total_hz: "total HZ",
        total_rv_needed: "RV requis",
        total_rejected: "rejetes",
        total_needs_more_data: "donnees requises"
      },
      pipeline: "Entonnoir pipeline",
      status: "Distribution des statuts",
      hz: "Statistiques HZ",
      falsePositive: "Raisons false-positive",
      distance: "Classes de distance",
      radius: "Tailles planetaires",
      top: "Top candidats",
      tess: "Couverture TESS",
      distanceColumn: "Distance",
      noHits: "Aucun resultat",
      spcArtHigh: "SPC_ART score eleve"
    }
  }[state.lang] || {};
  const statusLabels = ["SPC_STRONG", "SPC_FOLLOWUP_READY", "SPC", "SPC_ART", "NEEDS_MORE_DATA", "EB_RISK", "REJECTED", "IGNORE"];
  const hzLabels = ["ZU_HEISS", "OPT_HZ_INNEN", "KONSERVATIVE_HZ", "OPT_HZ_AUSSEN", "ZU_KALT"];
  const distanceRows = countBuckets(candidates, ["0-25 ly", "25-50 ly", "50-75 ly", "75-100 ly", "100-150 ly", "150-200 ly"], (candidate) => {
    const distance = Number(candidate.distance || 0);
    if (distance < 25) return "0-25 ly";
    if (distance < 50) return "25-50 ly";
    if (distance < 75) return "50-75 ly";
    if (distance < 100) return "75-100 ly";
    if (distance < 150) return "100-150 ly";
    if (distance < 200) return "150-200 ly";
    return "";
  });
  const radiusRows = countBuckets(candidates, ["<1 R_E", "1-1.5 R_E", "1.5-2 R_E", "2-4 R_E", "4-6 R_E", ">6 R_E"], (candidate) => {
    const radius = Number(candidate.radius || 0);
    if (radius < 1) return "<1 R_E";
    if (radius < 1.5) return "1-1.5 R_E";
    if (radius < 2) return "1.5-2 R_E";
    if (radius < 4) return "2-4 R_E";
    if (radius < 6) return "4-6 R_E";
    return ">6 R_E";
  });
  const falsePositiveRows = [
    { label: "Odd-Even", count: countWhere(candidates, (c) => /BAD|MISMATCH|ODD_EVEN/.test(`${c.oddEvenResult} ${matrixText(c)}`.toUpperCase())) },
    { label: "SAP/PDCSAP Mismatch", count: countWhere(candidates, (c) => /MISMATCH|SAP_PDCSAP/.test(`${c.sapPdcsapMatch} ${matrixText(c)}`.toUpperCase())) },
    { label: "Rotation", count: countWhere(candidates, (c) => /ROTATION|ALIAS/.test(`${c.rotationRisk} ${matrixText(c)}`.toUpperCase())) },
    { label: "BY Dra", count: countWhere(candidates, (c) => matrixText(c).includes("BY_DRA")) },
    { label: "Datenluecken", count: countWhere(candidates, (c) => /HIGH|MEDIUM|GAP|LUECK/.test(`${c.dataGapRisk} ${matrixText(c)}`.toUpperCase())) },
    { label: "EB Risk", count: countWhere(candidates, (c) => matrixText(c).includes("EB_RISK")) },
    { label: "Secondary Eclipse", count: countWhere(candidates, (c) => /SECONDARY|ECLIPSE/.test(`${c.secondaryEclipse} ${matrixText(c)}`.toUpperCase()) && String(c.secondaryEclipse || "").toUpperCase() !== "NO") },
    { label: "V-Shape", count: countWhere(candidates, (c) => /V_SHAPE|V-SHAPE/.test(matrixText(c))) }
  ];
  const statusRows = countBuckets(candidates, statusLabels, matrixStatusBucket);
  const hzRows = countBuckets(candidates, hzLabels, (candidate) => candidate.hz || "");
  const funnelRows = [
    { label: "scanned_stars", count: data.summary?.total || candidates.length },
    { label: "stars_with_tess_data", count: countWhere(candidates, (c) => expectedTransits(c) > 0 || Number(c.matrixSectors || 0) > 0) },
    { label: "detected_signals", count: countWhere(candidates, (c) => Number(c.period || 0) > 0 && Number(c.snr || 0) > 0) },
    { label: "transit_candidates", count: countWhere(candidates, (c) => expectedTransits(c) > 0) },
    { label: "SPC_ART", count: countWhere(candidates, isSpcArt) },
    { label: "SPC_FOLLOWUP_READY", count: countWhere(candidates, isSpcPrepCandidate) },
    { label: "SPC", count: countWhere(candidates, isSpc) },
    { label: "SPC_STRONG", count: countWhere(candidates, isSpcStrong) },
    { label: "RV_NEEDED", count: countWhere(candidates, isRvNeeded) },
    { label: "REJECTED", count: countWhere(candidates, (c) => matrixStatusBucket(c) === "REJECTED" || c.color === "red") }
  ];
  const top20 = [...candidates]
    .sort((a, b) => {
      const hzRank = { KONSERVATIVE_HZ: 0, OPT_HZ_INNEN: 1, OPT_HZ_AUSSEN: 2, ZU_KALT: 3, ZU_HEISS: 4 };
      return (Number(b.evidenceScore || 0) - Number(a.evidenceScore || 0))
        || ((hzRank[a.hz] ?? 9) - (hzRank[b.hz] ?? 9))
        || (Number(a.distance || 0) - Number(b.distance || 0));
    })
    .slice(0, 20);
  const coverageTop = [...candidates]
    .filter((candidate) => expectedTransits(candidate) > 0)
    .sort((a, b) => Number(b.evidenceScore || 0) - Number(a.evidenceScore || 0))
    .slice(0, 12);
  const followups = [
    ["SPC_RV_NEEDED", candidates.filter(isRvNeeded).slice(0, 12)],
    ["SPC_FOLLOWUP_READY", candidates.filter((c) => matrixText(c).includes("FOLLOWUP_READY")).slice(0, 12)],
    ["HZ_RECHECK", candidates.filter((c) => c.isViolet && /RECHECK|REVISIT|TESS/.test(matrixText(c))).slice(0, 12)],
    ["NEEDS_MORE_DATA", candidates.filter((c) => matrixStatusBucket(c) === "NEEDS_MORE_DATA").slice(0, 12)],
    [copy.spcArtHigh, candidates.filter((c) => isSpcArt(c) && Number(c.evidenceScore || 0) >= 65).slice(0, 12)]
  ];
  const kpis = [
    ["total_scanned", data.summary?.total || candidates.length],
    ["total_candidates", countWhere(candidates, (c) => expectedTransits(c) > 0)],
    ["total_spc", countWhere(candidates, isSpc)],
    ["total_spc_strong", countWhere(candidates, isSpcStrong)],
    ["total_spc_prep_yellow", countWhere(candidates, isSpcPrepCandidate)],
    ["total_hz", countWhere(candidates, (c) => c.isViolet)],
    ["total_rv_needed", countWhere(candidates, isRvNeeded)],
    ["total_rejected", countWhere(candidates, (c) => matrixStatusBucket(c) === "REJECTED" || c.color === "red")],
    ["total_needs_more_data", countWhere(candidates, (c) => matrixStatusBucket(c) === "NEEDS_MORE_DATA")]
  ];

  els.matrixStats.innerHTML = `
    <div class="matrix-stat-kpis">
      ${kpis.map(([label, value]) => `<div class="matrix-stat-card"><span>${copy.kpis?.[label] || label}</span><strong>${formatNumber(value)}</strong></div>`).join("")}
    </div>
    <div class="matrix-stat-grid">
      <article class="matrix-stat-box"><h3>${copy.pipeline}</h3><div class="matrix-stat-list">${renderStatRows(funnelRows)}</div></article>
      <article class="matrix-stat-box"><h3>${copy.status}</h3><div class="matrix-stat-list">${renderStatRows(statusRows)}</div></article>
      <article class="matrix-stat-box"><h3>${copy.hz}</h3><div class="matrix-stat-list">${renderStatRows(hzRows)}</div></article>
      <article class="matrix-stat-box"><h3>${copy.falsePositive}</h3><div class="matrix-stat-list">${renderStatRows(falsePositiveRows)}</div></article>
      <article class="matrix-stat-box"><h3>${copy.distance}</h3><div class="matrix-stat-list">${renderStatRows(distanceRows)}</div></article>
      <article class="matrix-stat-box"><h3>${copy.radius}</h3><div class="matrix-stat-list">${renderStatRows(radiusRows)}</div></article>
    </div>
    <div class="matrix-followup-grid">
      <article class="matrix-stat-box">
        <h3>${copy.top}</h3>
        <div class="table-wrap">
          <table class="docs-table">
            <thead><tr><th>TIC</th><th>Evidence</th><th>HZ</th><th>${copy.distanceColumn}</th><th>Status</th></tr></thead>
            <tbody>${top20.map((c) => `<tr><td><strong>TIC ${c.tic}</strong></td><td>${formatMaybe(c.evidenceScore, 0)}</td><td>${formatMaybe(c.hz)}</td><td>${c.distance} ly</td><td>${formatMaybe(c.matrixClass, c.matrixStatus)}</td></tr>`).join("")}</tbody>
          </table>
        </div>
      </article>
      <article class="matrix-stat-box">
        <h3>${copy.tess}</h3>
        <div class="table-wrap">
          <table class="docs-table">
            <thead><tr><th>TIC</th><th>expected_transits</th><th>visible_transits</th><th>coverage_percent</th></tr></thead>
            <tbody>${coverageTop.map((c) => `<tr><td><strong>TIC ${c.tic}</strong></td><td>${expectedTransits(c)}</td><td>${visibleMatrixTransits(c)}</td><td>${coveragePercent(c)}%</td></tr>`).join("")}</tbody>
          </table>
        </div>
      </article>
    </div>
    <div class="matrix-followup-grid">
      ${followups.map(([label, items]) => `<article class="matrix-stat-box"><h3>${label}</h3><div class="matrix-mini-list">${items.length ? items.map(candidateChip).join("") : `<span class="muted">${copy.noHits}</span>`}</div></article>`).join("")}
    </div>
  `;
}
