import { analytics, ensureCountryBucket, saveAnalyticsStore, loadAnalyticsStore, saveSelfFilterPreference, setupGlobalAnalytics } from './state.js';
import { t, currentLocale } from './i18n.js';
import { data } from './dataLoader.js';
import { renderAdmin } from './components/followupPanel.js';

export function countryNameFromCode(code) {
  const safeCode = String(code || "").toUpperCase();
  if (!/^[A-Z]{2}$/.test(safeCode)) return t("table_country_unknown");
  try {
    const formatter = new Intl.DisplayNames([currentLocale(), "en-US"], { type: "region", fallback: "code" });
    const name = formatter.of(safeCode);
    return name || safeCode;
  } catch (_) {
    return safeCode;
  }
}

export function extractRegionFromLocaleTag(tag) {
  if (!tag) return null;
  try {
    if (typeof Intl.Locale === "function") {
      const locale = new Intl.Locale(String(tag));
      const region = (locale.region || locale.maximize().region || "").toUpperCase();
      if (/^[A-Z]{2}$/.test(region)) return region;
    }
  } catch (_) {}

  const cleaned = String(tag).replace(/_/g, "-");
  const parts = cleaned.split("-");
  for (let i = parts.length - 1; i >= 0; i -= 1) {
    const token = String(parts[i] || "").toUpperCase();
    if (/^[A-Z]{2}$/.test(token)) return token;
  }
  return null;
}

export function resolveCountryFromLocale() {
  const localeCandidates = []
    .concat(Array.isArray(navigator.languages) ? navigator.languages : [])
    .concat([navigator.language])
    .filter(Boolean);
  for (const tag of localeCandidates) {
    const code = extractRegionFromLocaleTag(tag);
    if (code) return { code, name: countryNameFromCode(code), source: `browser-locale (${tag})` };
  }
  return null;
}

export function resolveCountry() {
  return Promise.resolve().then(() => {
    const fromLocale = resolveCountryFromLocale();
    if (fromLocale) return fromLocale;
    return { code: "UN", name: "Unknown", source: "unresolved" };
  });
}

export function transferSessionCountry(fromCode, toCode, toName) {
  const from = ensureCountryBucket(fromCode, t("table_country_unknown"));
  const to = ensureCountryBucket(toCode, toName || t("table_country_unknown"));
  from.views = Math.max(0, (from.views || 0) - 1);
  from.sessions = Math.max(0, (from.sessions || 0) - 1);
  to.views = (to.views || 0) + 1;
  to.sessions = (to.sessions || 0) + 1;
  if (analytics.sessionCounted && analytics.sessionCountCountryCode === fromCode) {
    analytics.sessionCountCountryCode = toCode;
  }
  saveAnalyticsStore();
}

export function migrateUnknownHistory(toCode, toName) {
  if (!analytics.store || toCode === "UN") return false;
  const countries = analytics.store.countries || {};
  const unknown = countries.UN;
  if (!unknown) return false;
  const hasOtherHistory = Object.entries(countries).some(([code, item]) => {
    if (code === "UN") return false;
    return (item.views || 0) > 0 || (item.sessions || 0) > 0 || (item.totalDurationSeconds || 0) > 0;
  });
  if (hasOtherHistory) return false;
  const target = ensureCountryBucket(toCode, toName || countryNameFromCode(toCode));
  target.views = (target.views || 0) + (unknown.views || 0);
  target.sessions = (target.sessions || 0) + (unknown.sessions || 0);
  target.totalDurationSeconds = (target.totalDurationSeconds || 0) + (unknown.totalDurationSeconds || 0);
  delete analytics.store.countries.UN;
  saveAnalyticsStore();
  return true;
}

export function rollbackCurrentSessionCount() {
  if (!analytics.store || !analytics.sessionCounted) return;
  analytics.store.totalViews = Math.max(0, (analytics.store.totalViews || 0) - 1);
  analytics.store.totalSessions = Math.max(0, (analytics.store.totalSessions || 0) - 1);
  const bucket = ensureCountryBucket(analytics.sessionCountCountryCode || "UN", analytics.countryName || t("table_country_unknown"));
  bucket.views = Math.max(0, (bucket.views || 0) - 1);
  bucket.sessions = Math.max(0, (bucket.sessions || 0) - 1);
  analytics.sessionCounted = false;
  saveAnalyticsStore();
}

export function setSelfFilterEnabled(value) {
  const enabled = Boolean(value);
  analytics.selfFilterEnabled = enabled;
  saveSelfFilterPreference(enabled);
  if (enabled) rollbackCurrentSessionCount();
  if (!enabled && !analytics.sessionCounted) {
    if (!analytics.store) analytics.store = loadAnalyticsStore();
    analytics.store.totalViews += 1;
    analytics.store.totalSessions += 1;
    analytics.store.lastVisitAt = new Date().toISOString();
    const bucket = ensureCountryBucket(analytics.countryCode || "UN", analytics.countryName || t("table_country_unknown"));
    bucket.views += 1;
    bucket.sessions += 1;
    analytics.sessionCounted = true;
    analytics.sessionCountCountryCode = analytics.countryCode || "UN";
    saveAnalyticsStore();
  }
  setupGlobalAnalytics();
  renderAdmin();
}

export function startAnalyticsTracking() {
  analytics.store = loadAnalyticsStore();
  analytics.sessionStartedAt = Date.now();
  analytics.sessionClosed = false;
  analytics.sessionCounted = false;
  analytics.sessionCountCountryCode = "UN";

  if (!analytics.selfFilterEnabled) {
    analytics.store.totalViews += 1;
    analytics.store.totalSessions += 1;
    analytics.store.lastVisitAt = new Date().toISOString();

    const unknownBucket = ensureCountryBucket("UN", t("table_country_unknown"));
    unknownBucket.views += 1;
    unknownBucket.sessions += 1;
    analytics.sessionCounted = true;
    saveAnalyticsStore();
  }

  resolveCountry().then((country) => {
    analytics.countryCode = country.code;
    analytics.countryName = country.name;
    analytics.countrySource = country.source || t("admin_country_source_unknown");
    analytics.countryResolved = true;
    if (country.code !== "UN") {
      const migrated = migrateUnknownHistory(country.code, country.name);
      if (!migrated) transferSessionCountry("UN", country.code, country.name);
    }
    renderAdmin();
  });
}

export function finalizeAnalyticsSession() {
  if (analytics.sessionClosed) return;
  analytics.sessionClosed = true;
  if (!analytics.sessionCounted) return;
  if (!analytics.store) analytics.store = loadAnalyticsStore();
  const elapsedSeconds = Math.max(1, Math.round((Date.now() - analytics.sessionStartedAt) / 1000));
  analytics.store.totalDurationSeconds += elapsedSeconds;
  const bucket = ensureCountryBucket(analytics.countryCode, analytics.countryName);
  bucket.totalDurationSeconds = (bucket.totalDurationSeconds || 0) + elapsedSeconds;
  saveAnalyticsStore();
}
