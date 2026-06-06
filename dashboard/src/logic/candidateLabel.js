import { t } from '../i18n.js';
import { state } from '../state.js';

export function candidateLabel(candidate) {
  return (candidate.displayLabels || [])[0] || candidate.matrixClass || candidate.matrixStatus || candidate.status || candidate.markierungsKlasse || "UNKNOWN";
}

export function recheckChip(candidate) {
  const status = candidate.recheckStatus || "NO_PLANNED_RECHECK";
  const cls = {
    LIVE_NOW: "live",
    UPCOMING: "upcoming",
    WAITING_DATA: "waiting",
    NO_PLANNED_RECHECK: "none"
  }[status] || "none";
  return `<span class="recheck-chip ${cls}">${status}</span>`;
}
