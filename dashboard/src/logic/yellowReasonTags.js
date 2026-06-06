import { t, formatMaybe } from '../i18n.js';

export const yellowTagLabels = {
  Y_NTR_LOW: "wenige Transits",
  Y_LONG_PERIOD: "lange Periode",
  Y_DATA_GAP: "Datenluecken",
  Y_ACTIVITY_RISK: "Sternaktivitaet / BY Dra Risiko",
  Y_SYSTEMATICS: "moegliche Systematik",
  Y_SAP_PDCSAP_MISMATCH: "SAP/PDCSAP uneinheitlich",
  Y_ODD_EVEN_MISSING: "Odd-Even noch nicht geprueft",
  Y_MANUAL_REVIEW: "manuelles Review noetig",
  Y_STRONG_BUT_UNCONFIRMED: "starkes Signal, aber noch nicht bestaetigt"
};

export function reasonTagList(tags = []) {
  return tags.length
    ? `<div class="reason-tag-list">${tags.map((tag) => `<span class="reason-tag" title="${yellowTagLabels[tag] || tag}">${tag}</span>`).join("")}</div>`
    : `<span class="mini">${t("no_yellow_reason_tags")}</span>`;
}

export function nextCheckList(checks = []) {
  return checks.length
    ? `<div class="next-check-list">${checks.map((check) => `<span class="next-check">${check}</span>`).join("")}</div>`
    : `<span class="mini">${t("no_next_check")}</span>`;
}

export function candidateChip(candidate) {
  return `<button class="chip" type="button" data-stat-tic="${candidate.tic}">TIC ${candidate.tic} \u00b7 ${formatMaybe(candidate.evidenceScore, 0)}</button>`;
}
