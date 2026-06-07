import { state } from '../state.js';
import { t, formatNumber, formatFloat, formatMaybe, formatDate, formatSectorList, currentLocale } from '../i18n.js';
import { els, data, isSpcPrepCandidate, matrixText, countWhere, expectedTransits, localizedBaseColorLabel, colorClass, colorName, candidateVisualClass, candidateLabel, shortText, candidateNotes, followupShortLabel, top20Candidates, followupCandidates } from '../dataLoader.js';

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

export function publicMatrixCandidates() {
  const term = els.globalSearch.value.trim().toLowerCase();
  return publicVisibleCandidates().filter((candidate) => matchesCandidate(candidate, term));
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

export function renderKpis() {
  const publicRows = publicVisibleCandidates();
  

  document.getElementById("kpiTotal").textContent = formatNumber(data.summary.total);
  document.getElementById("kpiGreen").textContent = formatNumber(countWhere(publicRows, (candidate) => candidate.color === "green"));
  document.getElementById("kpiYellow").textContent = formatNumber(countWhere(publicRows, (candidate) => candidate.color === "yellow" && !isSpcPrepCandidate(candidate)));
  document.getElementById("kpiSpcPrep").textContent = formatNumber(countWhere(publicRows, isSpcPrepCandidate));
  document.getElementById("kpiRed").textContent = formatNumber(countWhere(publicRows, (candidate) => candidate.color === "red"));
  document.getElementById("kpiViolet").textContent = formatNumber(countWhere(publicRows, (candidate) => candidate.isViolet));
  document.getElementById("lcCount").textContent = formatNumber(data.lightcurveCandidates?.length || 0);
  document.getElementById("generatedAt").textContent = new Date(data.generatedAt).toLocaleTimeString(currentLocale(), {
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function renderVisitorKpis() {
  const candidates = publicVisibleCandidates();
  const tess = countWhere(candidates, (candidate) => expectedTransits(candidate) > 0 || Number(candidate.matrixSectors || 0) > 0);
  const spcStrong = countWhere(candidates, (candidate) => candidate.color === "green" || /SPC_STRONG|SPC_RV_NEEDED|SPC_FOLLOWUP_READY/.test(matrixText(candidate)));
  const recheck = countWhere(candidates, (candidate) => /NEEDS_MORE|SPC_ART|ACTIVE|ARTIFACT|RECHECK|EB_RISK/.test(matrixText(candidate)));
  const kpiCopy = {
    de: [
      ["Sterne analysiert", data.summary?.total || candidates.length, "Gaia/TIC-Manifest"],
      ["Sterne mit TESS-Daten", tess, "Sektor- oder Transitdaten"],
      ["Kandidaten gesamt", candidates.length, "Matrix-Eintraege"],
      ["SPC / starke Planetenkandidaten", spcStrong, "streng priorisiert"],
      ["HZ-Kandidaten", data.summary?.violet || countWhere(candidates, (c) => c.isViolet), "violett/HZ-Kontext"],
      ["Recheck / Artefaktverdacht", recheck, "gelb/unsicher"]
    ],
    en: [
      ["Stars scanned", data.summary?.total || candidates.length, "Gaia/TIC manifest"],
      ["Stars with TESS data", tess, "sector or transit data"],
      ["Candidates total", candidates.length, "matrix entries"],
      ["SPC / strong planet candidates", spcStrong, "strictly prioritized"],
      ["HZ candidates", data.summary?.violet || countWhere(candidates, (c) => c.isViolet), "violet/HZ context"],
      ["Recheck / artifact concern", recheck, "yellow/uncertain"]
    ],
    fr: [
      ["Etoiles analysees", data.summary?.total || candidates.length, "manifeste Gaia/TIC"],
      ["Etoiles avec donnees TESS", tess, "donnees secteur ou transit"],
      ["Candidats au total", candidates.length, "entrees matrice"],
      ["SPC / candidats planetaires forts", spcStrong, "priorisation stricte"],
      ["Candidats HZ", data.summary?.violet || countWhere(candidates, (c) => c.isViolet), "contexte violet/HZ"],
      ["Recheck / suspicion artefact", recheck, "jaune/incertain"]
    ]
  };
  const cards = kpiCopy[state.lang] || kpiCopy.de;
  els.visitorKpis.innerHTML = cards.map(([label, value, note]) => `
    <article class="visitor-kpi">
      <span>${label}</span>
      <strong>${formatNumber(value)}</strong>
      <span>${note}</span>
    </article>
  `).join("");
}

export function renderTopCandidates() {
  const rows = top20Candidates();
  if (!rows.length) {
    els.topCandidateRows.innerHTML = `<tr><td colspan="8">${t("top_candidates_empty")}</td></tr>`;
    if (els.topCandidatesRow) els.topCandidatesRow.innerHTML = `<span class="muted">${t("top_candidates_empty")}</span>`;
    renderFollowupCandidates();
    return;
  }
  els.topCandidateRows.innerHTML = rows.map((candidate, index) => {
    const rowClass = candidateVisualClass(candidate);
    return `
      <tr data-profile-tic="${candidate.tic}">
        <td>${index + 1}</td>
        <td><strong>TIC ${candidate.tic}</strong></td>
        <td>${formatFloat(candidate.distance, 2)}</td>
        <td>${formatFloat(candidate.period, 4)}</td>
        <td>${formatMaybe(candidate.hz)}</td>
        <td>${formatFloat(candidate.evidenceScore, 0)}</td>
        <td><span class="pill ${rowClass}">${candidateLabel(candidate)}</span></td>
        <td class="wrap-cell">${shortText(`${candidate.followupStrength === "STRONG" ? "FOLLOWUP_STRONG · " : ""}${candidateNotes(candidate)}`)}</td>
      </tr>
    `;
  }).join("");
  if (els.topCandidatesRow) {
    els.topCandidatesRow.innerHTML = rows.slice(0, 20).map((candidate) => {
      const rowClass = candidateVisualClass(candidate);
      return `
        <button class="top-candidate-chip" type="button" data-tic="${candidate.tic}">
          <strong>TIC ${candidate.tic}</strong>
          <span class="pill ${rowClass}">${candidateLabel(candidate)}</span>
          <span class="top-chip-meta">E ${formatFloat(candidate.evidenceScore, 0)} · ${candidate.distance} ly</span>
        </button>
      `;
    }).join("");
  }
  if (els.topCandidatesCount) {
    els.topCandidatesCount.textContent = formatNumber(rows.length);
  }
  renderFollowupCandidates();
}

export function renderFollowupCandidates() {
  const rows = followupCandidates();
  els.followupCandidateCount.textContent = formatNumber(rows.length);
  els.followupCandidateRows.innerHTML = rows.length ? rows.map((candidate) => `
    <button class="followup-item" type="button" data-followup-tic="${candidate.tic}">
      <strong>TIC ${candidate.tic}</strong>
      <span class="pill ${candidateVisualClass(candidate)}">${followupShortLabel(candidate)}</span>
      <span class="followup-meta">
        E${formatMaybe(candidate.evidenceScore, 0)} · ${formatFloat(candidate.distance, 1)} ly
      </span>
    </button>
  `).join("") : `<span class="muted">${t("followup_candidates_empty")}</span>`;
}

const PAGE_SIZE = 20;

export function renderTable() {
  let rows = publicMatrixCandidates();
  const sortBy = state.sortBy || "evidence";
  const sortOrder = state.sortOrder || "desc";
  rows = [...rows].sort((a, b) => {
    let va, vb;
    switch (sortBy) {
      case "evidence": va = a.evidenceScore || 0; vb = b.evidenceScore || 0; break;
      case "distance": va = a.distance || 0; vb = b.distance || 0; break;
      case "snr": va = a.snr || 0; vb = b.snr || 0; break;
      case "transits": va = expectedTransits(a) || 0; vb = expectedTransits(b) || 0; break;
      case "hz": va = a.hz || ""; vb = b.hz || ""; break;
      default: va = a.evidenceScore || 0; vb = b.evidenceScore || 0;
    }
    if (sortBy === "hz") {
      const order = sortOrder === "asc" ? 1 : -1;
      return va.localeCompare(vb) * order;
    }
    return sortOrder === "desc" ? vb - va : va - vb;
  });
  const total = rows.length;
  const term = els.globalSearch.value.trim().toLowerCase();
  const tableCount = document.getElementById("tableCount");
  if (tableCount) tableCount.textContent = `${formatNumber(total)} ${t("table_count_label")}`;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (state.tablePage >= totalPages) state.tablePage = totalPages - 1;
  if (state.tablePage < 0) state.tablePage = 0;
  const start = state.tablePage * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);
  if (!total) {
    els.rows.innerHTML = `<tr><td colspan="5">${term ? t("table_empty_search") : t("table_empty_filter")}</td></tr>`;
    const nav = document.getElementById("tablePageNav");
    if (nav) nav.innerHTML = "";
    return;
  }
  els.rows.innerHTML = pageRows.map((candidate) => {
    const rowClass = candidateVisualClass(candidate);
    const hzBadge = candidate.hz ? `<span class="table-hz-badge">${candidate.hz}</span>` : "";
    let prio = "—";
    let prioClass = "";
    const evidence = candidate.evidenceScore || 0;
    if (evidence >= 80 || (candidate.color === "green" && candidate.hz)) { prio = "Hoch"; prioClass = "prio-high"; }
    else if (evidence >= 50 || candidate.color === "green") { prio = "Mittel"; prioClass = "prio-mid"; }
    else { prio = "Niedrig"; prioClass = "prio-low"; }
    return `
    <tr data-tic="${candidate.tic}" class="${state.selected && state.selected.tic === candidate.tic ? "active-row" : ""}">
      <td><strong>TIC ${candidate.tic}</strong>${hzBadge}</td>
      <td><span class="pill ${rowClass}">${candidateLabel(candidate)}</span></td>
      <td>${formatFloat(candidate.evidenceScore, 0)}</td>
      <td>${candidate.distance ? candidate.distance + " ly" : "-"}</td>
      <td><span class="prio-pill ${prioClass}">${prio}</span></td>
    </tr>
  `;
  }).join("");
  renderPageNav(totalPages);
}

function renderPageNav(totalPages) {
  const nav = document.getElementById("tablePageNav");
  if (!nav) return;
  if (totalPages <= 1) { nav.innerHTML = ""; return; }
  const cur = state.tablePage;
  nav.innerHTML = `
    <button class="small-button page-btn" type="button" data-page="prev" ${cur === 0 ? "disabled" : ""}>‹</button>
    <span class="page-info">${cur + 1} / ${totalPages}</span>
    <button class="small-button page-btn" type="button" data-page="next" ${cur >= totalPages - 1 ? "disabled" : ""}>›</button>
  `;
}

export function setFollowupCollapsed(collapsed) {
  const panel = document.querySelector(".followup-subpanel");
  if (!panel || !els.toggleFollowupList) return;
  panel.classList.toggle("is-collapsed", Boolean(collapsed));
  els.toggleFollowupList.setAttribute("aria-expanded", collapsed ? "false" : "true");
  els.toggleFollowupList.title = collapsed ? t("followup_expand") : t("followup_collapse");
  els.toggleFollowupList.innerHTML = collapsed ? '<i data-lucide="chevron-down"></i>' : '<i data-lucide="chevron-up"></i>';
  if (window.lucide) window.lucide.createIcons();
}
