import { state } from '../state.js';
import { t, formatMaybe, formatFloat } from '../i18n.js';
import { els, data, isSpcPrepCandidate, colorName, localizedBaseColorLabel, candidateVisualClass, colorClass, publicCandidatePool, publicVisibleCandidates, top20Candidates, reasonTagList, nextCheckList, formatNumber, formatDate, formatSectorList } from '../dataLoader.js';
import { renderFinalDecisionPanel as renderNewFdPanel, initPanelListeners } from './finalDecisionPanel.js';

export function candidateChip(candidate) {
  return `<button class="chip" type="button" data-stat-tic="${candidate.tic}">TIC ${candidate.tic} · ${formatMaybe(candidate.evidenceScore, 0)}</button>`;
}

export function candidateGroupLabel(candidate) {
  if (isSpcPrepCandidate(candidate)) return "SPC Prep (gelb)";
  return colorName(candidate);
}

export function renderFinalDecisionPanel(candidate) {
  var fd = candidate.finalDecision;
  if (!fd) return "";

  var statusClass = (fd.status || "").toLowerCase().replace(/_/g, "-");
  var statusLabel = fd.status || "UNKNOWN";
  var statusGerman = statusLabel;
  if (statusLabel === "EXOFOP_CANDIDATE") statusGerman = "ExoFOP bereit";
  else if (statusLabel === "DATA_LIMITED_SECTORS") statusGerman = "Wenige Daten (Sektoren)";
  else if (statusLabel === "DATA_LIMITED_TRANSITS") statusGerman = "Wenige Daten (Transits)";
  else if (statusLabel === "NO_PLANET") statusGerman = "Kein Planet";
  else if (statusLabel === "RECHECK_ACTIVITY") statusGerman = "Aktivit\u00e4t pr\u00fcfen";

  var signalQuality = fd.signal_quality || "unknown";
  var dataQuality = fd.data_quality || "unknown";

  var signalColor = "#66736f";
  if (signalQuality === "weak") signalColor = "#bf3e36";
  else if (signalQuality === "medium") signalColor = "#b88220";
  else if (signalQuality === "strong") signalColor = "#147a68";

  var dataColor = "#66736f";
  if (dataQuality === "low") dataColor = "#bf3e36";
  else if (dataQuality === "sufficient") dataColor = "#b88220";
  else if (dataQuality === "high") dataColor = "#147a68";

  var passed_checks = fd.passed_checks || [];
  var warning_checks = fd.warning_checks || [];
  var failed_checks = fd.failed_checks || [];
  var not_run_checks = fd.not_run_checks || [];

  var checkTree = fd.check_tree || [];
  var treeHtml = "";
  for (var i = 0; i < checkTree.length; i++) {
    var check = checkTree[i];
    var statusIcon = "o";
    var statusColor = "#66736f";
    if (check.status === "passed") { statusIcon = String.fromCharCode(10003); statusColor = "#147a68"; }
    else if (check.status === "warning") { statusIcon = String.fromCharCode(9888); statusColor = "#b88220"; }
    else if (check.status === "failed") { statusIcon = String.fromCharCode(10007); statusColor = "#bf3e36"; }

    treeHtml += '<div class="check-tree-item" style="margin-left:' + (i * 20) + 'px">';
    treeHtml += '<span style="color:' + statusColor + ';margin-right:8px">' + statusIcon + '</span>';
    treeHtml += '<span>' + check.name + '</span>';
    if (check.reason) {
      treeHtml += '<div class="check-reason">' + check.reason + '</div>';
    }
    treeHtml += '</div>';
  }

  var allChecks = [
    { name: "TESS Data", status: passed_checks.indexOf("TESS Data") >= 0 ? "passed" : (warning_checks.indexOf("TESS Data") >= 0 ? "warning" : (failed_checks.indexOf("TESS Data") >= 0 ? "failed" : "not_run")) },
    { name: "Signal Detection", status: passed_checks.indexOf("Signal Detection") >= 0 ? "passed" : (warning_checks.indexOf("Signal Detection") >= 0 ? "warning" : (failed_checks.indexOf("Signal Detection") >= 0 ? "failed" : "not_run")) },
    { name: "Folded Light Curve", status: passed_checks.indexOf("Folded Light Curve") >= 0 ? "passed" : (warning_checks.indexOf("Folded Light Curve") >= 0 ? "warning" : (failed_checks.indexOf("Folded Light Curve") >= 0 ? "failed" : "not_run")) },
    { name: "Sector Coverage", status: passed_checks.indexOf("Sector Coverage") >= 0 ? "passed" : (warning_checks.indexOf("Sector Coverage") >= 0 ? "warning" : (failed_checks.indexOf("Sector Coverage") >= 0 ? "failed" : "not_run")) },
    { name: "Transit Count", status: passed_checks.indexOf("Transit Count") >= 0 ? "passed" : (warning_checks.indexOf("Transit Count") >= 0 ? "warning" : (failed_checks.indexOf("Transit Count") >= 0 ? "failed" : "not_run")) },
    { name: "SAP/PDCSAP", status: passed_checks.indexOf("SAP/PDCSAP") >= 0 ? "passed" : (warning_checks.indexOf("SAP/PDCSAP") >= 0 ? "warning" : (failed_checks.indexOf("SAP/PDCSAP") >= 0 ? "failed" : "not_run")) },
    { name: "Odd/Even", status: passed_checks.indexOf("Odd/Even") >= 0 ? "passed" : (warning_checks.indexOf("Odd/Even") >= 0 ? "warning" : (failed_checks.indexOf("Odd/Even") >= 0 ? "failed" : "not_run")) },
    { name: "Secondary Eclipse", status: passed_checks.indexOf("Secondary Eclipse") >= 0 ? "passed" : (warning_checks.indexOf("Secondary Eclipse") >= 0 ? "warning" : (failed_checks.indexOf("Secondary Eclipse") >= 0 ? "failed" : "not_run")) },
    { name: "Activity/Rotation", status: passed_checks.indexOf("Activity/Rotation") >= 0 ? "passed" : (warning_checks.indexOf("Activity/Rotation") >= 0 ? "warning" : (failed_checks.indexOf("Activity/Rotation") >= 0 ? "failed" : "not_run")) }
  ];

  var heatmapColors = {
    "passed": "#147a68",
    "warning": "#b88220",
    "failed": "#bf3e36",
    "not_run": "#e2e3e5"
  };

  var heatmapHtml = "";
  for (var j = 0; j < allChecks.length; j++) {
    var c = allChecks[j];
    heatmapHtml += '<div class="heatmap-cell" style="background:' + heatmapColors[c.status] + '">' + c.name + '</div>';
  }

  var heatmapLegend = '<div class="heatmap-legend"><span style="color:#147a68">ok</span><span style="color:#b88220">warn</span><span style="color:#bf3e36">fail</span><span style="color:#6c757d">-</span></div>';

  var nextActionHtml = "";
  if (fd.next_action) {
    nextActionHtml = '<div class="fd-next-action"><div class="fd-next-label">Nachste Aktion</div><div class="fd-next-value">' + fd.next_action + '</div></div>';
  }

  var blockersHtml = "";
  var blockers = fd.blockers || [];
  if (blockers.length > 0) {
    blockersHtml = '<div class="fd-blockers"><div class="fd-blockers-label">Blocker</div><div class="fd-blockers-list">' + blockers.join(", ") + '</div></div>';
  }

  var html = '<div class="final-decision-panel">';
  html += '<div class="fd-header">';
  html += '<div class="fd-title"><strong>FINAL DECISION</strong><span class="final-decision-badge ' + statusClass + '">' + statusGerman + '</span></div>';
  html += '<div class="fd-subtitle">' + (fd.reason || "") + '</div>';
  html += '</div>';

  html += '<div class="fd-matrix">';
  html += '<div class="matrix-row"><div class="matrix-axis-y">Signalqualitat</div>';
  html += '<div class="matrix-quadrant" style="border-color:' + signalColor + '">';
  html += '<div class="quadrant-label">' + signalQuality.toUpperCase() + '</div>';
  html += '<div class="quadrant-desc">Transit-Signal Qualitat</div></div></div>';
  html += '<div class="matrix-row"><div class="matrix-axis-y">Datenqualitat</div>';
  html += '<div class="matrix-quadrant" style="border-color:' + dataColor + '">';
  html += '<div class="quadrant-label">' + dataQuality.toUpperCase() + '</div>';
  html += '<div class="quadrant-desc">TESS Daten Umfang</div></div></div>';
  html += '<div class="matrix-x-axis">Schwach - Stark</div>';
  html += '</div>';

  html += '<div class="fd-section"><div class="fd-section-title">Prufbaum</div><div class="check-tree">' + treeHtml + '</div></div>';
  html += '<div class="fd-section"><div class="fd-section-title">Evidence Heatmap</div><div class="heatmap-grid">' + heatmapHtml + '</div>' + heatmapLegend + '</div>';
  html += nextActionHtml + blockersHtml;
  html += '</div>';

  return html;
}

export function renderSelected() {
  const candidate = state.selected || publicCandidatePool()[0] || publicVisibleCandidates()[0];
  if (!candidate) {
    if (els.selectedCardTitle) els.selectedCardTitle.textContent = "Kein Kandidat";
    if (els.selectedCardTic) els.selectedCardTic.textContent = "-";
    if (els.selectedCard) els.selectedCard.innerHTML = "";
    return;
  }
  state.selected = candidate;
  if (els.selectedCardTitle) {
    els.selectedCardTitle.textContent = `Ausgewaehlter Kandidat`;
  }
  if (els.selectedCardTic) {
    els.selectedCardTic.textContent = `TIC ${candidate.tic}`;
  }
  const matrixStatus = formatMaybe(candidate.matrixStatus);
  const matrixClass = formatMaybe(candidate.matrixClass);
  const evidence = formatMaybe(candidate.evidenceScore);
  const matrixReason = formatMaybe(candidate.decisionReason, candidate.reason || "-");
  const matrixNext = formatMaybe(candidate.nextStep);
  const depthText = Number.isFinite(Number(candidate.depthPpt)) ? `${formatFloat(candidate.depthPpt, 2)} ppt` : "-";
  const durationText = Number.isFinite(Number(candidate.durationHours)) ? `${formatFloat(candidate.durationHours, 2)} h` : "-";
  const raText = Number.isFinite(Number(candidate.raDeg)) ? `${formatFloat(candidate.raDeg, 5)}°` : "-";
  const decText = Number.isFinite(Number(candidate.decDeg)) ? `${formatFloat(candidate.decDeg, 5)}°` : "-";
  const localizedBaseColor = localizedBaseColorLabel(candidate);
  const displayLabels = candidate.displayLabels || [];
  const chips = [
    `<span class="chip ${candidate.color}">${localizedBaseColor}</span>`,
    candidate.isViolet ? `<span class="chip violet">${t("chip_violet_hz")}</span>` : "",
    candidate.hz ? `<span class="chip">${candidate.hz}</span>` : "",
    ...displayLabels.map((label) => `<span class="chip ${candidateVisualClass(candidate)}">${label}</span>`),
    candidate.matrixStatus && !displayLabels.includes(candidate.matrixStatus) ? `<span class="chip ${candidateVisualClass(candidate)}">${t("chip_matrix_prefix", { value: candidate.matrixStatus })}</span>` : "",
    candidate.evidenceScore !== null && candidate.evidenceScore !== undefined ? `<span class="chip ${candidateVisualClass(candidate)}">${t("chip_evidence_prefix", { value: candidate.evidenceScore })}</span>` : "",
    candidate.lightcurveImg ? `<span class="chip">${t("chip_curve_available")}</span>` : ""
  ].filter(Boolean).join("");
  els.selectedCard.innerHTML = `
    ${renderNewFdPanel(candidate)}
    ${renderFinalDecisionPanel(candidate)}
    <div class="selected-title">
      <strong>TIC ${candidate.tic}</strong>
      <span class="pill ${colorClass(candidate)}">${candidateGroupLabel(candidate)}</span>
    </div>
    <div class="chips">${chips}</div>
    <div class="details-grid compact">
      <div class="detail"><span>${t("detail_distance")}</span><strong>${candidate.distance} ly</strong></div>
      <div class="detail"><span>${t("detail_period")}</span><strong>${candidate.period} d</strong></div>
      <div class="detail"><span>${t("detail_snr")}</span><strong>${candidate.snr}</strong></div>
      <div class="detail"><span>${t("detail_transits_visible")}</span><strong>${candidate.visibleTransits}/${candidate.transits}</strong></div>
      <div class="detail"><span>${t("detail_radius")}</span><strong>${candidate.radius || "-"} R_E</strong></div>
      <div class="detail"><span>${t("detail_ra")}</span><strong>${raText}</strong></div>
      <div class="detail"><span>${t("detail_dec")}</span><strong>${decText}</strong></div>
      <div class="detail"><span>Sektoren</span><strong>${candidate.observedSectorCount || "-"}</strong></div>
    </div>
    <div class="notice">
      <strong>Ordner:</strong> ${candidate.folder || "-"}
    </div>
  `;
  initPanelListeners(els.selectedCard);
}

export function renderYellowReasonPanel() {
  const selected = state.selected || top20Candidates()[0] || publicCandidatePool()[0];
  if (!selected) return;
  const summary = selected.yellowSummary || (
    selected.color === "yellow" || (selected.reasonTags || []).some((tag) => tag.startsWith("Y_"))
      ? t("yellow_summary_default")
      : t("yellow_summary_not_yellow")
  );
  els.yellowSelectedReason.innerHTML = `
    <p>${summary}</p>
    <div><strong>${t("followup_label")}:</strong> ${formatMaybe(selected.followupStrength)}</div>
    <div><strong>${t("reason_tags_label")}:</strong>${reasonTagList(selected.reasonTags || [])}</div>
    <div><strong>${t("next_check_label")}:</strong>${nextCheckList(selected.nextChecks || [])}</div>
    <div class="notice matrix-note"><strong>${t("why_label")}</strong><span>${formatMaybe(selected.decisionReason, selected.reason)}</span></div>
  `;
}
