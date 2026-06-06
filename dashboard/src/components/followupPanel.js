import { analytics, globalAnalytics, isAdminLoggedIn, loadAnalyticsStore } from '../state.js';
import { t, formatNumber, formatDuration, formatDateTime } from '../i18n.js';
import { els, data, exofopReadiness, isSpcPrepCandidate, isRvNeeded, isSpcStrong, matrixText, followupRank } from '../dataLoader.js';
import { matchesCandidate } from './candidateList.js';

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

export function exofopCriteriaFulfilled(candidate) {
  return exofopReadiness(candidate) === "READY_FOR_EXOFOP";
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

function hzPriority(candidate) {
  return candidate.isViolet ? 0 : (candidate.hz && candidate.hz !== "ZU_HEISS" ? 1 : 2);
}

export function renderAdmin() {
  if (!analytics.store) analytics.store = loadAnalyticsStore();
  const loggedIn = isAdminLoggedIn();
  els.adminLoginCard.classList.toggle("admin-hidden", loggedIn);
  els.adminStatsWrap.classList.toggle("admin-hidden", !loggedIn);

  if (!loggedIn) {
    els.adminLoginHint.textContent = t("admin_login_hint");
    return;
  }

  const statusLabel =
    globalAnalytics.mode === "active" ? t("status_active") :
    globalAnalytics.mode === "loading" ? t("status_loading") :
    globalAnalytics.mode === "paused_filter" ? t("status_paused_filter") :
    globalAnalytics.mode === "paused" ? t("status_paused_localhost") :
    globalAnalytics.mode === "error" ? t("status_error") :
    t("status_inactive");
  const detailsLabel =
    globalAnalytics.mode === "active" ? t("analytics_tracking_to", { endpoint: globalAnalytics.endpoint }) :
    globalAnalytics.mode === "loading" ? t("analytics_loading") :
    globalAnalytics.mode === "paused_filter" ? t("analytics_self_filter_active") :
    globalAnalytics.mode === "paused" ? t("analytics_local_disabled") :
    globalAnalytics.mode === "error" ? (globalAnalytics.error || t("status_unknown_error")) :
    t("analytics_endpoint_missing");
  els.adminGlobalStatus.textContent = statusLabel;
  els.adminGlobalDetails.textContent = detailsLabel;
  const hasDashboard = Boolean(globalAnalytics.dashboardUrl);
  els.adminGlobalDashboardLink.href = hasDashboard ? globalAnalytics.dashboardUrl : "#";
  els.adminGlobalDashboardLink.textContent = hasDashboard ? globalAnalytics.dashboardUrl : t("not_set");
  els.adminGlobalDashboardLink.style.pointerEvents = hasDashboard ? "auto" : "none";
  els.adminGlobalDashboardLink.style.opacity = hasDashboard ? "1" : "0.6";
  els.adminGoatTitle.textContent = t("admin_goat_title");
  els.adminGoatText.textContent = t("admin_goat_text");
  els.adminGoatButton.href = hasDashboard ? globalAnalytics.dashboardUrl : "#";
  els.adminGoatButton.style.pointerEvents = hasDashboard ? "auto" : "none";
  els.adminGoatButton.style.opacity = hasDashboard ? "1" : "0.6";
  els.adminGoatButtonLabel.textContent = t("admin_goat_button");
  els.adminLocalTitle.textContent = t("admin_local_title");
  els.adminLocalText.textContent = t("admin_local_text");
  els.adminSelfFilterStatus.textContent = analytics.selfFilterEnabled ? t("admin_self_filter_on") : t("admin_self_filter_off");
  els.adminToggleSelfFilterLabel.textContent = analytics.selfFilterEnabled
    ? t("admin_self_filter_disable")
    : t("admin_self_filter_enable");

  const store = analytics.store;
  const avgDuration = store.totalSessions > 0 ? store.totalDurationSeconds / store.totalSessions : 0;
  els.adminViews.textContent = formatNumber(store.totalViews);
  els.adminSessions.textContent = formatNumber(store.totalSessions);
  els.adminAvgDuration.textContent = formatDuration(avgDuration);
  els.adminLastVisit.textContent = formatDateTime(store.lastVisitAt);
  els.adminCurrentCountry.textContent = `${analytics.countryName} (${analytics.countryCode})`;
  els.adminCountrySource.textContent = analytics.countrySource || "-";

  const rows = Object.values(store.countries)
    .sort((a, b) => (b.views || 0) - (a.views || 0))
    .map((item) => {
      const avg = (item.sessions || 0) > 0 ? item.totalDurationSeconds / item.sessions : 0;
      return `
        <tr>
          <td><strong>${item.name || t("table_country_unknown")} (${item.code || "UN"})</strong></td>
          <td>${formatNumber(item.views || 0)}</td>
          <td>${formatNumber(item.sessions || 0)}</td>
          <td>${formatDuration(item.totalDurationSeconds || 0)}</td>
          <td>${formatDuration(avg)}</td>
        </tr>
      `;
    }).join("");
  els.adminCountryRows.innerHTML = rows || `<tr><td colspan="5">${t("no_entries")}</td></tr>`;

  const exofopRows = exofopUploadCandidates(els.globalSearch.value).map((candidate) => `
    <tr>
      <td data-label="TIC"><strong>TIC ${candidate.tic}</strong></td>
      <td data-label="${t("exofop_criteria_label")}">
        <span class="pill ${exofopCriteriaFulfilled(candidate) ? "green" : "yellow"}">
          ${exofopCriteriaFulfilled(candidate) ? t("yes_label") : t("no_review_open")}
        </span>
      </td>
    </tr>
  `).join("");
  els.adminExofopRows.innerHTML = exofopRows || `<tr><td colspan="2">${t("admin_exofop_empty")}</td></tr>`;
}
