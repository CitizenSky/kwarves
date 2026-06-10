import { state } from '../state.js';
import { t, formatMaybe, formatFloat } from '../i18n.js';
import { els, data, isSpcPrepCandidate, colorName, localizedBaseColorLabel, candidateVisualClass, colorClass, publicCandidatePool, publicVisibleCandidates, top20Candidates, reasonTagList, nextCheckList, formatNumber, formatDate, formatSectorList, candidateLabel } from '../dataLoader.js';
import { renderFinalDecisionPanel as renderNewFdPanel, initPanelListeners } from './finalDecisionPanel.js';
import { computeFinalDecision } from '../logic/finalDecision.js';

export function candidateChip(candidate) {
  return `<button class="chip" type="button" data-stat-tic="${candidate.tic}">TIC ${candidate.tic} · ${formatMaybe(candidate.evidenceScore, 0)}</button>`;
}

export function candidateGroupLabel(candidate) {
  if (isSpcPrepCandidate(candidate)) return "SPC Prep (gelb)";
  return colorName(candidate);
}

export function renderFinalDecisionPanel(candidate) {
  var fd = computeFinalDecision(candidate);
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

function renderExecutiveSummary(candidate) {
  const items = [];
  const fd = computeFinalDecision(candidate);

  if (candidate.hz) items.push({ type: "good", text: `HZ Kandidat (${candidate.hz})` });
  if (candidate.distance) items.push({ type: "good", text: `${candidate.distance} Lichtjahre` });
  if (candidate.snr) items.push({ type: "good", text: `SNR ${formatFloat(candidate.snr, 1)}` });
  if (candidate.visibleTransits) items.push({ type: "good", text: `${candidate.visibleTransits} sichtbare Transits` });
  if (candidate.isViolet) items.push({ type: "good", text: "HZ-Fokus Kandidat" });
  if (candidate.evidenceScore >= 80) items.push({ type: "good", text: `Evidence ${formatFloat(candidate.evidenceScore, 0)} — hohe Priorität` });

  if (fd && fd.check_tree) {
    fd.check_tree.forEach((check) => {
      if (check.status === "warning") items.push({ type: "warn", text: check.reason || check.name });
      if (check.status === "failed") items.push({ type: "bad", text: check.reason || check.name });
    });
  }
  if (fd && fd.blockers) {
    fd.blockers.forEach((b) => items.push({ type: "warn", text: b }));
  }

  if (!items.length) return "";

  const icons = { good: "✓", warn: "⚠", bad: "✗" };
  return `
    <div class="executive-summary">
      ${items.map((item) => `
        <div class="executive-item executive-${item.type}">
          <span class="executive-icon">${icons[item.type]}</span>
          <span>${item.text}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderActionCard(candidate) {
  const fd = computeFinalDecision(candidate);
  const evidence = candidate.evidenceScore || 0;

  let priorityLevel = "low";
  let priorityLabel = "Niedrig";
  if (evidence >= 80 || (candidate.color === "green" && candidate.hz)) {
    priorityLevel = "high";
    priorityLabel = "Hoch";
  } else if (evidence >= 50 || candidate.color === "green") {
    priorityLevel = "medium";
    priorityLabel = "Mittel";
  }

  const tasks = [];
  if (candidate.nextStep) tasks.push(candidate.nextStep);
  if (candidate.decisionReason && !tasks.includes(candidate.decisionReason)) tasks.push(candidate.decisionReason);
  if (fd) {
    if (fd.next_action) tasks.push(fd.next_action);
    if (fd.blockers) fd.blockers.forEach((b) => { if (!tasks.includes(b)) tasks.push(b); });
    if (fd.check_tree) {
      fd.check_tree.forEach((check) => {
        if (check.status === "warning" || check.status === "failed") {
          const label = check.reason ? `${check.name}: ${check.reason}` : check.name;
          if (!tasks.includes(label)) tasks.push(label);
        }
      });
    }
  }

  const reasonParts = [];
  if (fd && fd.reason) reasonParts.push(fd.reason);
  if (candidate.reason && !reasonParts.includes(candidate.reason)) reasonParts.push(candidate.reason);

  const signalText = fd ? `Signal: ${fd.signal_quality || "?"}` : "";
  const dataText = fd ? `Daten: ${fd.data_quality || "?"}` : "";
  const reasonText = reasonParts.length ? reasonParts.join(" · ") : "";

  return `
    <div class="action-card">
      <div class="action-card-header">
        <strong>N\u00e4chste Aktion</strong>
        <span class="action-priority priority-${priorityLevel}">${priorityLabel}</span>
      </div>
      ${tasks.length ? `<div class="action-tasks">${tasks.map((t) => `<div class="action-task">• ${t}</div>`).join("")}</div>` : ""}
      <div class="action-meta">
        ${signalText ? `<span>${signalText}</span>` : ""}
        ${dataText ? `<span>${dataText}</span>` : ""}
      </div>
      ${reasonText ? `<div class="action-reason">${reasonText}</div>` : ""}
    </div>
  `;
}

function compactStatus(candidate) {
  return candidateLabel(candidate) || candidate.matrixClass || candidate.matrixStatus || candidate.status || "-";
}

function nextActionText(candidate) {
  const fd = computeFinalDecision(candidate);
  return fd?.suggestedAction || candidate.nextStep || candidate.decisionReason || "Review candidate";
}

function progressStatus(status) {
  const value = String(status || "").toUpperCase();
  if (["PASS", "PASSED", "SUPPORTS", "CLEAN", "LOW_RISK", "OK", "NO_KNOWN_MATCH", "NO_LOCAL_BLEND_FLAG", "SHAPE_CLEAR", "STABLE"].includes(value)) return "pass";
  if (["FAIL", "FAILED", "RED_FP", "FALSE_POSITIVE", "KNOWN_FP_OR_EB", "POSSIBLE_BLEND", "RUWE_ELEVATED", "DUPLICATED_SOURCE", "UNSTABLE"].includes(value)) return "fail";
  if (["LOCKED", "NO_TESS_DATA", "WAIT_FOR_TESS", "NOT_AVAILABLE", "NOT_CHECKED", "NOT_COMPUTED"].includes(value)) return "locked";
  return "review";
}

function renderCandidateSummaryHeader(candidate) {
  const evidence = candidate.evidenceScore !== null && candidate.evidenceScore !== undefined ? formatFloat(candidate.evidenceScore, 0) : "-";
  const visible = candidate.matrixVisibleTransits ?? candidate.visibleTransits ?? "-";
  const total = candidate.matrixTransits ?? candidate.transits ?? "-";
  const summaryItems = [
    ["Status", compactStatus(candidate)],
    ["Distanz", candidate.distance ? `${candidate.distance} ly` : "-"],
    ["SNR", candidate.snr ? formatFloat(candidate.snr, 1) : "-"],
    ["Evidence", evidence],
    ["Visible Transits", `${visible}/${total}`],
    ["Next Action", nextActionText(candidate)]
  ];
  return `
    <section class="candidate-summary-header">
      <div class="candidate-summary-main">
        <span>Kandidat</span>
        <strong>TIC ${candidate.tic}</strong>
      </div>
      <div class="candidate-summary-grid">
        ${summaryItems.map(([label, value]) => `
          <div class="candidate-summary-item">
            <span>${label}</span>
            <strong>${value}</strong>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function checkFromTree(fd, name) {
  const item = (fd?.check_tree || []).find((check) => check.name === name);
  if (!item) return { status: "locked", reason: "not available" };
  return { status: item.status === "passed" ? "pass" : (item.status === "failed" ? "fail" : "review"), reason: item.reason || "" };
}

function renderVettingProgressTree(candidate) {
  const fd = computeFinalDecision(candidate);
  const mmClean = candidate.multiMethodCleanForExofop ?? candidate.multi_method_clean_for_exofop;
  const steps = [
    ["Signal Detection", checkFromTree(fd, "Signal Detection")],
    ["Data Quality", checkFromTree(fd, "TESS Data")],
    ["Transit Shape", { status: progressStatus(candidate.transitShape || candidate.transit_shape), reason: candidate.transitShape || candidate.transit_shape || "-" }],
    ["Single Transit Review", { status: progressStatus(candidate.individualTransitStatus || candidate.individual_transit_status || candidate.singleTransitStatus), reason: candidate.individualTransitStatus || candidate.singleTransitStatus || "pending" }],
    ["Odd/Even", { status: progressStatus(candidate.oddEvenResult), reason: candidate.oddEvenResult || "-" }],
    ["SAP vs PDCSAP", { status: progressStatus(candidate.sapPdcsapMatch), reason: candidate.sapPdcsapMatch || "-" }],
    ["Activity", { status: progressStatus(candidate.variabilityStatus || candidate.variability_status || candidate.rotationRisk), reason: candidate.variabilityStatus || candidate.rotationRisk || "-" }],
    ["Blend Check", { status: progressStatus(candidate.blendStatus || candidate.blend_status), reason: candidate.blendStatus || candidate.blend_status || "-" }],
    ["Multi-Method Evidence", { status: (candidate.multiMethodScore ?? candidate.multi_method_score ?? 0) >= 65 ? "pass" : "review", reason: `Score ${candidate.multiMethodScore ?? candidate.multi_method_score ?? "-"}/100` }],
    ["VVT", { status: "locked", reason: "manual review queue" }],
    ["EXOFOP Ready", { status: mmClean ? "pass" : "locked", reason: mmClean ? "core checks clean" : "blocked by open checks" }]
  ];
  return `
    <section class="vetting-progress-panel">
      <div class="section-title-row">
        <strong>Vetting Progress Tree</strong>
        <span>PASS / REVIEW / FAIL / LOCKED</span>
      </div>
      <div class="vetting-progress-grid">
        ${steps.map(([label, item]) => `
          <article class="vetting-step status-${item.status}">
            <span>${item.status.toUpperCase()}</span>
            <strong>${label}</strong>
            <p>${item.reason || "-"}</p>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}

function renderBlockingIssuesPanel(candidate) {
  const fd = computeFinalDecision(candidate);
  const blockers = [];
  (fd?.blockers || []).forEach((item) => blockers.push(item));
  const flagRows = candidate.methodEvidenceFlags || candidate.method_evidence_flags || [];
  flagRows.forEach((flag) => {
    if (flag.effect === "weaken" || flag.status === "BLOCKED") blockers.push(flag.reason || flag.status);
  });
  [
    ["Activity unclear", candidate.variabilityStatus || candidate.variability_status],
    ["Blend check pending", candidate.blendStatus || candidate.blend_status],
    ["Variability unresolved", candidate.variabilityStatus || candidate.variability_status],
    ["VVT not completed", "LOCKED"]
  ].forEach(([label, status]) => {
    const value = String(status || "").toUpperCase();
    if (!/CLEAN|SUPPORTS|NO_LOCAL_BLEND_FLAG/.test(value)) blockers.push(label);
  });
  const unique = [...new Set(blockers.filter(Boolean))].slice(0, 8);
  return `
    <section class="blocking-issues-panel">
      <div class="section-title-row">
        <strong>Why is this candidate NOT EXOFOP_READY?</strong>
        <span>${(candidate.multiMethodCleanForExofop ?? candidate.multi_method_clean_for_exofop) ? "Core checks clean" : "Open review items"}</span>
      </div>
      ${unique.length ? `<div class="blocking-list">${unique.map((item) => `<div class="blocking-item">${item}</div>`).join("")}</div>` : `<div class="notice">Keine blockierenden Punkte im aktuellen Dashboard-Datensatz.</div>`}
    </section>
  `;
}

export function renderSelected() {
  const candidate = state.selectedCandidate || state.selected;
  if (!candidate) {
    if (els.selectedCardTitle) els.selectedCardTitle.textContent = "Bitte Kandidaten auswaehlen";
    if (els.selectedCardTic) els.selectedCardTic.textContent = "";
    if (els.selectedCard) {
      els.selectedCard.innerHTML = `
        <div class="notice">
          Bitte Kandidaten auswaehlen, um Candidate Report, Scientific Evidence, Transit Informationen und Vetting Details zu sehen.
        </div>
      `;
    }
    return;
  }
  state.selected = candidate;
  state.selectedCandidate = candidate;
  state.activeCandidateId = candidate.tic;
  const detailLoadError = candidate._detailLoadError;
  const evidence = candidate.evidenceScore !== null && candidate.evidenceScore !== undefined ? formatFloat(candidate.evidenceScore, 0) : "-";
  const hzLabel = candidate.hz || "-";
  const distLabel = candidate.distance ? `${candidate.distance} ly` : "-";
  const snrLabel = candidate.snr ? formatFloat(candidate.snr, 1) : "-";
  const periodLabel = candidate.period ? `${formatFloat(candidate.period, 4)} d` : "-";
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
    candidate.lightcurveImg ? `<span class="chip">${t("chip_curve_available")}</span>` : ""
  ].filter(Boolean).join("");

  if (els.selectedCardTitle) {
    els.selectedCardTitle.textContent = `TIC ${candidate.tic}`;
  }
  if (els.selectedCardTic) {
    const meta = [];
    meta.push(`E ${evidence}`);
    if (hzLabel !== "-") meta.push(hzLabel);
    meta.push(distLabel);
    els.selectedCardTic.textContent = meta.join(" · ");
  }

  els.selectedCard.innerHTML = `
    ${detailLoadError ? `
      <div class="notice error-notice">
        <strong>Detaildaten konnten nicht geladen werden.</strong>
        <span>${detailLoadError.message || "Die Lazy-Detaildatei fehlt oder ist nicht erreichbar."}</span>
        ${detailLoadError.detail ? `<small>${detailLoadError.detail}</small>` : ""}
      </div>
    ` : ""}
    ${renderCandidateSummaryHeader(candidate)}
    ${renderVettingProgressTree(candidate)}
    ${renderBlockingIssuesPanel(candidate)}
    ${renderNewFdPanel(candidate)}
    ${renderExecutiveSummary(candidate)}
    <div class="chips">${chips}</div>
    <div class="selected-quick-metrics">
      <span class="pill ${colorClass(candidate)}">${candidateGroupLabel(candidate)}</span>
      <span class="pill">E ${evidence}</span>
      ${candidate.hz ? `<span class="pill hz-pill">${candidate.hz}</span>` : ""}
      <span class="pill">${distLabel}</span>
      <span class="pill">SNR ${snrLabel}</span>
    </div>
    ${renderActionCard(candidate)}
    <div class="details-grid compact">
      <div class="detail"><span>${t("detail_distance")}</span><strong>${distLabel}</strong></div>
      <div class="detail"><span>${t("detail_period")}</span><strong>${periodLabel}</strong></div>
      <div class="detail"><span>${t("detail_snr")}</span><strong>${snrLabel}</strong></div>
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
  const selected = state.selectedCandidate || state.selected;
  if (!selected) {
    els.yellowSelectedReason.innerHTML = `<p>Bitte Kandidaten auswaehlen.</p>`;
    return;
  }
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
