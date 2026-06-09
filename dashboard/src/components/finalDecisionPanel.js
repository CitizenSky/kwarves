import { computeFinalDecision } from '../logic/finalDecision.js';

const STATUS_LABELS = {
  "EXOFOP_CANDIDATE": "ExoFOP bereit",
  "GREEN_SPC": "Grün SPC",
  "YELLOW_RECHECK": "Recheck",
  "PURPLE_SPC_ART": "SPC Art",
  "RED_FP": "False Positive",
  "WAIT_FOR_TESS": "Warten auf TESS",
  "LOW_CONFIDENCE": "Niedrige Sicherheit",
  "DATA_LIMITED_SECTORS": "Wenige Daten (Sektoren)",
  "DATA_LIMITED_TRANSITS": "Wenige Daten (Transits)",
  "NO_PLANET": "Kein Planet",
  "RECHECK_ACTIVITY": "Aktivit\u00e4t pr\u00fcfen"
};

const HEATMAP_COLORS = {
  passed: "#147a68",
  warning: "#b88220",
  failed: "#bf3e36",
  not_run: "#e2e3e5"
};

const SIGNAL_COLORS = {
  weak: "#bf3e36",
  medium: "#b88220",
  strong: "#147a68"
};

const DATA_COLORS = {
  low: "#bf3e36",
  sufficient: "#b88220",
  high: "#147a68"
};

const NEXT_LABELS = {
  "wait_for_tess": "Auf TESS-Daten warten",
  "exclude": "Von Analyse ausschließen",
  "wait_for_more_sectors": "Auf weitere Sektoren warten",
  "wait_for_more_transits": "Auf weitere Transits warten",
  "manual_review_required": "Manuelle Überprüfung erforderlich",
  "rotation_activity_check": "Rotation/Activity separat prüfen",
  "prepare_exofop_upload": "ExoFOP-Upload vorbereiten"
};

const CHECK_ORDER = [
  "TESS Data",
  "Signal Detection",
  "Folded Light Curve",
  "Sector Coverage",
  "Transit Count",
  "Odd/Even",
  "Secondary Eclipse",
  "SAP/PDCSAP",
  "Activity/Rotation"
];

function loadCollapsed() {
  try { return localStorage.getItem("kwarves_fd_collapsed") !== "0"; }
  catch (_) { return true; }
}

function saveCollapsed(v) {
  try { localStorage.setItem("kwarves_fd_collapsed", v ? "1" : "0"); }
  catch (_) {}
}

function renderCheckTree(checkTree) {
  var html = "";
  for (var i = 0; i < checkTree.length; i++) {
    var check = checkTree[i];
    var icon = "○";
    var color = "#66736f";
    if (check.status === "passed") { icon = "✓"; color = "#147a68"; }
    else if (check.status === "warning") { icon = "⚠"; color = "#b88220"; }
    else if (check.status === "failed") { icon = "✗"; color = "#bf3e36"; }
    html += '<div class="ct-item"><span class="ct-icon" style="color:' + color + '">' + icon + '</span><span class="ct-name">' + check.name + '</span>';
    if (check.reason) html += '<div class="ct-reason">' + check.reason + '</div>';
    html += '</div>';
  }
  return html;
}

function renderHeatmap(checkTree) {
  var html = "";
  for (var i = 0; i < CHECK_ORDER.length; i++) {
    var name = CHECK_ORDER[i];
    var obj = null;
    for (var j = 0; j < checkTree.length; j++) {
      if (checkTree[j].name === name) { obj = checkTree[j]; break; }
    }
    var status = obj ? obj.status : "not_run";
    html += '<div class="hm-cell" style="background:' + HEATMAP_COLORS[status] + '" title="' + name + ': ' + status + '">' + name + '</div>';
  }
  var legend = '<div class="hm-legend"><span class="hm-dot" style="background:#147a68"></span>ok <span class="hm-dot" style="background:#b88220"></span>warn <span class="hm-dot" style="background:#bf3e36"></span>fail <span class="hm-dot" style="background:#e2e3e5"></span>—</div>';
  return '<div class="hm-grid">' + html + '</div>' + legend;
}

function renderBlockers(blockers) {
  if (!blockers || blockers.length === 0) return "";
  var html = '<div class="fd-blockers"><div class="fd-blockers-title">Blocker</div>';
  for (var i = 0; i < blockers.length; i++) {
    html += '<div class="fd-blocker-item">' + blockers[i] + '</div>';
  }
  return html + '</div>';
}

function renderSpcArtStage2(stage2) {
  if (!stage2 || !stage2.applies) return "";
  var missing = stage2.missingChecks && stage2.missingChecks.length ? stage2.missingChecks.join(", ") : "-";
  var blocking = stage2.blockingIssues && stage2.blockingIssues.length ? stage2.blockingIssues.join(" | ") : "-";
  var transitCount = stage2.transits && stage2.transits.length ? String(stage2.transits.length) : "-";
  var visibleCount = stage2.visibleTransits ?? "-";
  var depthScatter = stage2.depthScatterPpt ?? "-";
  var medianSingleSnr = stage2.medianSingleTransitSnr ?? "-";
  var plotAvailable = stage2.plotStatus === "PLOT_AVAILABLE" ? "Ja" : "Nein";
  var shapeSource = stage2.transitShapeSource || "-";
  var shapeScore = stage2.transitShapeScore ?? "-";
  var source = stage2.source || (stage2.fallbackUsed ? "RUNTIME_FALLBACK" : "DATA_BUILD");
  return '' +
    '<div class="fd-section"><div class="fd-section-title">SPC_ART Stage 2</div>' +
      '<div class="fd-kv"><span>Berechnet</span><strong>' + (stage2.stage2Completed === false ? "Nein" : "Ja") + '</strong></div>' +
      '<div class="fd-kv"><span>Quelle</span><strong>' + source + '</strong></div>' +
      '<div class="fd-kv"><span>Runtime-Fallback</span><strong>' + (stage2.fallbackUsed ? "Ja" : "Nein") + '</strong></div>' +
      '<div class="fd-kv"><span>Berechnungsstatus</span><strong>' + (stage2.computationStatus || "-") + '</strong></div>' +
      '<div class="fd-kv"><span>Warum SPC_ART</span><strong>Artifact/systematics concerns</strong></div>' +
      '<div class="fd-kv"><span>Fehlende Prüfung</span><strong>' + missing + '</strong></div>' +
      '<div class="fd-kv"><span>Fehlende Werte</span><strong>' + blocking + '</strong></div>' +
      '<div class="fd-kv"><span>Nächste Aktion</span><strong>' + (stage2.nextAction || "-") + '</strong></div>' +
      '<div class="fd-kv"><span>Einzeltransite</span><strong>' + (stage2.singleTransitStatus || "-") + ' (' + transitCount + ' Events)</strong></div>' +
      '<div class="fd-kv"><span>Sichtbare Transits</span><strong>' + visibleCount + '</strong></div>' +
      '<div class="fd-kv"><span>Depth Scatter</span><strong>' + depthScatter + ' ppt</strong></div>' +
      '<div class="fd-kv"><span>Median Single-SNR</span><strong>' + medianSingleSnr + '</strong></div>' +
      '<div class="fd-kv"><span>Plot verfügbar</span><strong>' + plotAvailable + ' · ' + (stage2.plotStatus || "-") + '</strong></div>' +
      '<div class="fd-kv"><span>Depth Stability</span><strong>' + (stage2.depthStability || "-") + ' · Score ' + (stage2.depthStabilityScore ?? "-") + '</strong></div>' +
      '<div class="fd-kv"><span>Folded LC</span><strong>' + (stage2.foldedLightCurveStatus || "-") + ' · Shape ' + (stage2.transitShape || stage2.transitShapeClass || "-") + '</strong></div>' +
      '<div class="fd-kv"><span>Shape-Quelle</span><strong>' + shapeSource + '</strong></div>' +
      '<div class="fd-kv"><span>Shape-Score</span><strong>' + shapeScore + '</strong></div>' +
      '<div class="fd-kv"><span>Activity</span><strong>' + (stage2.activityStatus || stage2.activityRotationStatus || "-") + '</strong></div>' +
    '</div>';
}

export function renderFinalDecisionPanel(candidate) {
  if (!candidate) return "";
  var fd = computeFinalDecision(candidate);
  if (!fd) return "";

  var collapsed = loadCollapsed();
  var statusClass = fd.status.toLowerCase().replace(/_/g, "-");
  var statusLabel = STATUS_LABELS[fd.status] || fd.status;
  var signalColor = SIGNAL_COLORS[fd.signal_quality] || "#66736f";
  var dataColor = DATA_COLORS[fd.data_quality] || "#66736f";
  var panelContentId = "fd-content-" + (candidate.tic || "0");
  var toggleIcon = collapsed ? "▶" : "▼";

  var nextHtml = "";
  if (fd.next_action && NEXT_LABELS[fd.next_action]) {
    nextHtml = '<div class="fd-next"><strong>Nächste Aktion:</strong> ' + NEXT_LABELS[fd.next_action] + '</div>';
  } else if (fd.suggestedAction) {
    nextHtml = '<div class="fd-next"><strong>Nächste Aktion:</strong> ' + fd.suggestedAction + '</div>';
  }

  var stageHtml = '<div class="fd-section"><div class="fd-section-title">Monitor / Vetting Stage 2</div>' +
    '<div class="fd-kv"><span>Monitor Status</span><strong>' + (fd.monitorStatus || "-") + '</strong></div>' +
    '<div class="fd-kv"><span>TESS Data Status</span><strong>' + (fd.dataStatus || "-") + '</strong></div>' +
    '<div class="fd-kv"><span>Vetting Stage 2</span><strong>' + (fd.vettingStage2Class || fd.status || "-") + '</strong></div>' +
    '<div class="fd-kv"><span>Suggested Action</span><strong>' + (fd.suggestedAction || NEXT_LABELS[fd.next_action] || "-") + '</strong></div>' +
    '<div class="fd-kv"><span>Decision Reason</span><strong>' + (fd.decisionReason || fd.reason || "-") + '</strong></div>' +
  '</div>';

  return '<div class="fd-panel">' +
    '<button class="fd-toggle" type="button" aria-expanded="' + String(!collapsed) + '" data-fd-target="' + panelContentId + '">' +
      '<span class="fd-toggle-icon">' + toggleIcon + '</span>' +
      '<span class="fd-toggle-label">FINAL DECISION</span>' +
      '<span class="fd-badge ' + statusClass + '">' + statusLabel + '</span>' +
    '</button>' +
      '<div id="' + panelContentId + '" class="fd-content"' + (collapsed ? ' style="display:none"' : "") + '>' +
      '<div class="fd-reason">' + (fd.reason || "") + '</div>' +
      nextHtml +
      stageHtml +
      renderSpcArtStage2(fd.spcArtStage2 || candidate.spcArtStage2) +
      '<div class="fd-matrix">' +
        '<div class="fd-matrix-row"><div class="fd-axis">Signalqualität</div><div class="fd-quadrant" style="border-color:' + signalColor + '"><div class="fd-quadrant-label">' + String(fd.signal_quality).toUpperCase() + '</div><div class="fd-quadrant-desc">Transit-Signal</div></div></div>' +
        '<div class="fd-matrix-row"><div class="fd-axis">Datenqualität</div><div class="fd-quadrant" style="border-color:' + dataColor + '"><div class="fd-quadrant-label">' + String(fd.data_quality).toUpperCase() + '</div><div class="fd-quadrant-desc">TESS-Abdeckung</div></div></div>' +
      '</div>' +
      '<div class="fd-section"><div class="fd-section-title">Prüfbaum</div><div class="ct-tree">' + renderCheckTree(fd.check_tree) + '</div></div>' +
      '<div class="fd-section"><div class="fd-section-title">Evidence Heatmap</div>' + renderHeatmap(fd.check_tree) + '</div>' +
      renderBlockers(fd.blockers) +
    '</div>' +
  '</div>';
}

export function initPanelListeners(containerEl) {
  containerEl.addEventListener("click", function (e) {
    var btn = e.target.closest(".fd-toggle");
    if (!btn) return;
    var targetId = btn.getAttribute("data-fd-target");
    var content = document.getElementById(targetId);
    if (!content) return;
    var isExpanded = btn.getAttribute("aria-expanded") === "true";
    var newCollapsed = isExpanded;
    content.style.display = newCollapsed ? "none" : "";
    btn.setAttribute("aria-expanded", String(!newCollapsed));
    var icon = btn.querySelector(".fd-toggle-icon");
    if (icon) icon.textContent = newCollapsed ? "▶" : "▼";
    saveCollapsed(newCollapsed);
  });
}
