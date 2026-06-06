import { formatNumber } from '../i18n.js';

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

export function notificationSeverityClass(item) {
  if (item.severity === "high") return "red";
  if (item.severity === "medium") return "yellow";
  return "gray";
}

export function formatNotificationValue(value, fallback = "-") {
  if (value === undefined || value === null || value === "") return fallback;
  return value;
}
