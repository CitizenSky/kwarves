export const DASHBOARD_UI_VERSION = "2026-06-02-r";

export const state = {
  colorFilter: "all",
  curveFilter: "all",
  tableLimit: "all",
  selected: null,
  selectedCurve: null,
  mapMode: "2d",
  tessMapMode: "3d",
  sceneReady: false,
  lang: "de"
};

export const LANGUAGE_KEY = "kwarves_ui_language_v1";
export const SUPPORTED_LANGS = ["de", "en", "fr"];
export const LANGUAGE_LOCALES = {
  de: "de-DE",
  en: "en-US",
  fr: "fr-FR"
};

export const ADMIN_USER = "Koni";
export const ADMIN_PASSWORD = "starfield";
export const ADMIN_LOGIN_KEY = "kwarves_admin_logged_in_v1";
export const ANALYTICS_STORE_KEY = "kwarves_local_analytics_v1";
export const ANALYTICS_SELF_FILTER_KEY = "kwarves_analytics_filter_self_v1";
export const PANEL_COLLAPSE_KEY = "kwarves_panel_collapsed_v4";
export const TESS_COMPARE_COLLAPSE_KEY = "kwarves_tess_compare_collapsed_v2";
export const SELECTED_CARD_COLLAPSE_KEY = "kwarves_selected_card_collapsed_v1";
export const GLOBAL_ANALYTICS_CONFIG = {
  provider: "goatcounter",
  endpoint: "https://koni.goatcounter.com/count",
  dashboardUrl: "https://koni.goatcounter.com",
  allowLocalhost: false
};

export const colors = {
  green: "#24a085",
  yellow: "#d08a24",
  spcPrep: "#e0b24a",
  red: "#d75047",
  violet: "#806cf0",
  gray: "#a9b4b0",
  sun: "#f4c96d"
};

export const analytics = {
  store: null,
  sessionStartedAt: Date.now(),
  sessionClosed: false,
  sessionCounted: false,
  sessionCountCountryCode: "UN",
  countryCode: "UN",
  countryName: "Unknown",
  countrySource: "unknown",
  countryResolved: false,
  selfFilterEnabled: false
};

export const globalAnalytics = {
  enabled: false,
  loaded: false,
  error: "",
  mode: "inactive",
  endpoint: "",
  dashboardUrl: ""
};

export const tessMission = {
  sourceCheckedAt: "2026-05-31",
  sectorDurationDays: 27.4,
  totalNumberedSectorsPlanned: 107,
  primaryMissionSectors: 26,
  year8Description:
    "Year 8 umfasst S97-S107; S97/98 sind 4-Orbit-Sektoren, danach folgen 9 gedrehte Ueberlappungssektoren.",
  geometryDescription:
    "Sektor-Footprint ca. 24x96 Grad; 4 Kameras in Streifenanordnung, Sektorlaenge typischerweise 27 Tage.",
  year8Sectors: [
    { sector: 97, start: "2025-09-15", end: "2025-11-09", arrangement: "Suedpol (4 Orbits)" },
    { sector: 98, start: "2025-11-09", end: "2026-01-05", arrangement: "Suedpol (4 Orbits)" },
    { sector: 99, start: "2026-01-05", end: "2026-02-02", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 100, start: "2026-02-02", end: "2026-03-01", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 101, start: "2026-03-01", end: "2026-03-27", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 102, start: "2026-03-27", end: "2026-04-21", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 103, start: "2026-04-21", end: "2026-05-17", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 104, start: "2026-05-17", end: "2026-06-13", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 105, start: "2026-06-13", end: "2026-07-11", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 106, start: "2026-07-11", end: "2026-08-09", arrangement: "Suedpol, 40 Grad Roll/Shift" },
    { sector: 107, start: "2026-08-09", end: "2026-09-07", arrangement: "Suedpol, 40 Grad Roll/Shift" }
  ]
};

export const tessYear8SectorSet = new Set(tessMission.year8Sectors.map((item) => item.sector));

export function buildTessSectorLayout(totalSectors) {
  const result = [];
  for (let sector = 1; sector <= totalSectors; sector += 1) {
    const index = sector - 1;
    const cycle = Math.floor(index / 13);
    const inCycle = index % 13;
    const angle = (inCycle / 13) * Math.PI * 2 - Math.PI / 2;
    const hemisphere = cycle % 2 === 0 ? -1 : 1;
    const radius = 0.56 + cycle * 0.185;
    const x = Math.cos(angle) * radius;
    const y = hemisphere * (0.36 + cycle * 0.03);
    const z = Math.sin(angle) * radius * 0.7;
    result.push({ sector, cycle, x, y, z });
  }
  return result;
}

export const tessSectorLayout = buildTessSectorLayout(tessMission.totalNumberedSectorsPlanned);

export function clampMapZoom(value) {
  return Math.max(0.75, Math.min(5, Number(value) || 1));
}

export function updateMapZoomLabel() {
  const el = document.getElementById("mapZoomValue");
  if (el) el.textContent = `${mapZoom.toFixed(1)}x`;
}

export let mapZoom = 1;

export function applyMapZoom(value) {
  mapZoom = clampMapZoom(value);
  updateMapZoomLabel();
}

export function isLocalHost(host) {
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

export function loadCollapsedPanelState() {
  try {
    const raw = localStorage.getItem(PANEL_COLLAPSE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_) {
    return {};
  }
}

export function saveCollapsedPanelState(stateMap) {
  try {
    localStorage.setItem(PANEL_COLLAPSE_KEY, JSON.stringify(stateMap || {}));
  } catch (_) {}
}

export function loadTessCompareCollapsed() {
  try {
    const value = localStorage.getItem(TESS_COMPARE_COLLAPSE_KEY);
    return value === null ? true : value === "1";
  } catch (_) {
    return true;
  }
}

export function loadSelectedCardCollapsed() {
  try {
    const value = localStorage.getItem(SELECTED_CARD_COLLAPSE_KEY);
    return value === null ? false : value === "1";
  } catch (_) {
    return false;
  }
}

export function collapseButtonState(button, collapsed) {
  if (!button) return;
  button.setAttribute("aria-expanded", collapsed ? "false" : "true");
}

export function emptyAnalyticsStore() {
  return {
    totalViews: 0,
    totalSessions: 0,
    totalDurationSeconds: 0,
    lastVisitAt: null,
    countries: {}
  };
}

export function loadAnalyticsStore() {
  try {
    const raw = localStorage.getItem(ANALYTICS_STORE_KEY);
    if (!raw) return emptyAnalyticsStore();
    const parsed = JSON.parse(raw);
    const base = emptyAnalyticsStore();
    return {
      totalViews: Number(parsed.totalViews) || 0,
      totalSessions: Number(parsed.totalSessions) || 0,
      totalDurationSeconds: Number(parsed.totalDurationSeconds) || 0,
      lastVisitAt: parsed.lastVisitAt || null,
      countries: parsed.countries && typeof parsed.countries === "object" ? parsed.countries : base.countries
    };
  } catch (_) {
    return emptyAnalyticsStore();
  }
}

export function saveAnalyticsStore() {
  if (!analytics.store) return;
  localStorage.setItem(ANALYTICS_STORE_KEY, JSON.stringify(analytics.store));
}

export function loadSelfFilterPreference() {
  try {
    const raw = localStorage.getItem(ANALYTICS_SELF_FILTER_KEY);
    if (raw === "1") return true;
    if (raw === "0") return false;
  } catch (_) {}
  return isLocalHost(location.hostname);
}

export function saveSelfFilterPreference(value) {
  try {
    localStorage.setItem(ANALYTICS_SELF_FILTER_KEY, value ? "1" : "0");
  } catch (_) {}
}

export function isAdminLoggedIn() {
  try {
    return sessionStorage.getItem(ADMIN_LOGIN_KEY) === "1";
  } catch (_) {
    return false;
  }
}

export function setAdminLoggedIn(value) {
  try {
    if (value) sessionStorage.setItem(ADMIN_LOGIN_KEY, "1");
    else sessionStorage.removeItem(ADMIN_LOGIN_KEY);
  } catch (_) {}
}

export function fetchJsonWithTimeout(url, timeoutMs = 4500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return fetch(url, { signal: controller.signal, cache: "no-store" }).then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    }).finally(() => clearTimeout(timer));
  } catch(_) {
    clearTimeout(timer);
    return Promise.reject(_);
  }
}

export function normalizeGlobalAnalyticsConfig() {
  const endpoint = String(GLOBAL_ANALYTICS_CONFIG.endpoint || "").trim();
  const dashboardUrl = String(GLOBAL_ANALYTICS_CONFIG.dashboardUrl || "").trim();
  return {
    provider: String(GLOBAL_ANALYTICS_CONFIG.provider || "").toLowerCase(),
    endpoint,
    dashboardUrl: dashboardUrl || (endpoint ? endpoint.replace(/\/count\/?$/, "") : ""),
    allowLocalhost: Boolean(GLOBAL_ANALYTICS_CONFIG.allowLocalhost)
  };
}

export function ensureCountryBucket(code, name = "") {
  if (!analytics.store) analytics.store = loadAnalyticsStore();
  const safeCode = String(code || "UN").toUpperCase();
  if (!analytics.store.countries[safeCode]) {
    analytics.store.countries[safeCode] = {
      code: safeCode,
      name: name || "Unknown",
      views: 0,
      sessions: 0,
      totalDurationSeconds: 0
    };
  } else if (name && name !== "Unknown") {
    analytics.store.countries[safeCode].name = name;
  }
  return analytics.store.countries[safeCode];
}

export function setupGlobalAnalytics() {
  const cfg = normalizeGlobalAnalyticsConfig();
  globalAnalytics.endpoint = cfg.endpoint;
  globalAnalytics.dashboardUrl = cfg.dashboardUrl;
  globalAnalytics.mode = "inactive";
  globalAnalytics.error = "";

  if (!cfg.endpoint) {
    globalAnalytics.enabled = false;
    globalAnalytics.mode = "inactive";
    return;
  }

  if (!/^https?:\/\//i.test(cfg.endpoint)) {
    globalAnalytics.enabled = false;
    globalAnalytics.mode = "error";
    globalAnalytics.error = "Endpoint must start with http:// or https://.";
    return;
  }

  if (cfg.provider !== "goatcounter") {
    globalAnalytics.enabled = false;
    globalAnalytics.mode = "error";
    globalAnalytics.error = "Only GoatCounter is supported directly at the moment.";
    return;
  }

  if (analytics.selfFilterEnabled) {
    globalAnalytics.enabled = false;
    globalAnalytics.mode = "paused_filter";
    if (window.goatcounter) window.goatcounter.no_onload = true;
    return;
  }

  if (isLocalHost(location.hostname) && !cfg.allowLocalhost) {
    globalAnalytics.enabled = false;
    globalAnalytics.mode = "paused";
    return;
  }

  if (document.querySelector('script[data-kwarves-global-analytics="goatcounter"]')) {
    globalAnalytics.enabled = true;
    globalAnalytics.mode = "active";
    return;
  }

  const script = document.createElement("script");
  script.async = true;
  script.src = "https://gc.zgo.at/count.js";
  script.setAttribute("data-goatcounter", cfg.endpoint);
  script.setAttribute("data-kwarves-global-analytics", "goatcounter");
  script.setAttribute("data-goatcounter-settings", JSON.stringify({ allow_local: cfg.allowLocalhost }));
  script.onload = () => {
    globalAnalytics.enabled = true;
    globalAnalytics.loaded = true;
    globalAnalytics.mode = "active";
  };
  script.onerror = () => {
    globalAnalytics.enabled = false;
    globalAnalytics.mode = "error";
    globalAnalytics.error = "Tracking script could not be loaded (blocker/network/CSP).";
  };
  document.head.appendChild(script);
  globalAnalytics.enabled = true;
  globalAnalytics.mode = "loading";
}
