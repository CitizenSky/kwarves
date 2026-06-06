import { els, notifications } from './dataLoader.js';
import { collapseButtonState, loadCollapsedPanelState, saveCollapsedPanelState } from './state.js';
import { t, formatNumber, formatDate, formatDateTime, buildTessScheduleState } from './i18n.js';
import { notificationSeverityClass, formatNotificationValue } from './logic/renderHelpers.js';
import { colorClass } from './logic/colorFor.js';
import { draw2dMap } from './components/starMap2D.js';
import { resize3d } from './components/starMap3D.js';
import { drawTessSector2d, updateTessSector3dData, resizeTessSector3d } from './components/tessMissionControl.js';
import { renderVisitorCharts } from './main.js';

let toastTimer;

export function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2400);
}

export function renderNotificationBadge() {
  const count = Number(notifications.total || notifications.items?.length || 0);
  if (!els.notificationBadge) return;
  els.notificationBadge.textContent = count > 99 ? "99+" : String(count);
  els.notificationBadge.classList.toggle("show", count > 0);
}

export function setPanelCollapsed(panelId, collapsed, store = true) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  panel.classList.toggle("is-collapsed", Boolean(collapsed));
  const button = document.querySelector(`.panel-collapse-toggle[data-collapse-target="${panelId}"]`);
  collapseButtonState(button, Boolean(collapsed));
  if (store) {
    const panelState = loadCollapsedPanelState();
    panelState[panelId] = Boolean(collapsed);
    saveCollapsedPanelState(panelState);
  }
  if (!collapsed && panelId === "statisticsPanel") {
    window.requestAnimationFrame(() => renderVisitorCharts());
  }
  if (!collapsed && panelId === "mapPanel") {
    void panel.clientHeight;
    window.requestAnimationFrame(() => {
      draw2dMap();
      resize3d();
      const tessState = buildTessScheduleState();
      drawTessSector2d(tessState);
      updateTessSector3dData(tessState);
      resizeTessSector3d();
    });
  }
}

export function initPanelCollapseControls() {
  const persisted = loadCollapsedPanelState();
  document.querySelectorAll(".panel[id]").forEach((panel) => {
    const panelId = panel.id;
    const header = panel.querySelector(".panel-header");
    if (!header) return;

    let actions = header.querySelector(".map-header-actions") || header.querySelector(".panel-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "panel-actions";
      const moved = Array.from(header.children).slice(1);
      moved.forEach((item) => actions.appendChild(item));
      header.appendChild(actions);
    }

    let button = actions.querySelector(`.panel-collapse-toggle[data-collapse-target="${panelId}"]`);
    if (!button) {
      button = document.createElement("button");
      button.className = "icon-button panel-collapse-toggle";
      button.type = "button";
      button.setAttribute("data-collapse-target", panelId);
      button.setAttribute("aria-controls", panelId);
      button.innerHTML = '<i data-lucide="chevron-up"></i>';
      actions.appendChild(button);
    }

    const hasPersistedState = Object.prototype.hasOwnProperty.call(persisted, panelId);
    const defaultCollapsed = true;
    const isCollapsed = hasPersistedState ? Boolean(persisted[panelId]) : defaultCollapsed;
    panel.classList.toggle("is-collapsed", isCollapsed);
    collapseButtonState(button, isCollapsed);

    button.addEventListener("click", () => {
      const nowCollapsed = !panel.classList.contains("is-collapsed");
      setPanelCollapsed(panelId, nowCollapsed, true);
    });
  });
}

export function renderNotifications() {
  const items = notifications.items || [];
  const counts = notifications.counts || {};
  els.notificationTitle.textContent = t("notifications_title");
  els.notificationSummary.innerHTML = `
    <span>${items.length
      ? t("notifications_summary", {
        total: formatNumber(notifications.total || items.length),
        live: formatNumber(counts.liveNow || 0),
        upcoming: formatNumber(counts.upcoming || 0),
        waiting: formatNumber(counts.waitingData || 0)
      })
      : t("notifications_empty")}</span>
    <span>${t("notifications_updated", { date: notifications.generatedAt ? formatDateTime(notifications.generatedAt) : "-" })}</span>
  `;
  els.notificationList.innerHTML = items.length ? items.map((item) => {
    const changed = item.changes?.length || 0;
    const sectors = (item.newSectors || []).map((sector) => `S${sector}`).join(", ");
    const recheckLine = t("notification_recheck_line", {
      status: item.recheckStatus || "-",
      current: item.currentSector ? `S${item.currentSector}` : "-",
      next: item.nextPlannedSector ? `S${item.nextPlannedSector}` : "-",
      date: item.estimatedDataAvailable ? formatDate(item.estimatedDataAvailable) : "-"
    });
    return `
      <button class="notification-item" type="button" data-notification-tic="${item.tic}">
        <strong>TIC ${item.tic} <span class="pill ${notificationSeverityClass(item)}">${item.recheckStatus || item.type}</span></strong>
        <p>${item.summary || recheckLine}</p>
        <p>${recheckLine}</p>
        <p>${changed ? t("notification_change_count", { count: changed }) : ""}${sectors ? ` \u00b7 ${t("notification_new_sectors", { sectors })}` : ""}</p>
      </button>
    `;
  }).join("") : `<div class="notification-item"><p>${t("notifications_empty")}</p></div>`;
  renderNotificationBadge();
}

export function openNotifications() {
  renderNotifications();
  els.notificationPanel.classList.add("open");
  showToast(t("toast_notifications", { count: formatNumber(notifications.total || notifications.items?.length || 0) }));
}

export function closeNotifications() {
  els.notificationPanel.classList.remove("open");
}
