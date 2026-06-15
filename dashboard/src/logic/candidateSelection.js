export const SELECTION_PANEL_KEYS = Object.freeze([
  "candidateSummary",
  "vettingProgressTree",
  "blockingIssues",
  "multiMethodEvidence",
  "lightCurve",
  "matrixSelection",
  "starMap",
  "tessCoverage"
]);

export function createCandidateSelectionSnapshot(candidate, options = {}) {
  if (!candidate) return null;
  const {
    detailedCandidate = null,
    source = "table",
    currentCurveFilter = "all",
    curveForCandidate = () => null,
    curveMatchesFilter = () => true
  } = options;
  const selectedCandidate = detailedCandidate || candidate;
  const selectedCurve = curveForCandidate(selectedCandidate) || null;
  const resetCurveFilter = Boolean(
    selectedCurve &&
    source !== "curve" &&
    !curveMatchesFilter(selectedCurve, currentCurveFilter)
  );

  return {
    selected: selectedCandidate,
    selectedCandidate,
    activeCandidateId: selectedCandidate.tic,
    selectedCurve,
    curveFilter: resetCurveFilter ? "all" : currentCurveFilter,
    resetCurveFilter,
    source,
    panels: [...SELECTION_PANEL_KEYS]
  };
}

export function applyCandidateSelectionSnapshot(state, snapshot) {
  if (!state || !snapshot) return null;
  state.selected = snapshot.selected;
  state.selectedCandidate = snapshot.selectedCandidate;
  state.activeCandidateId = snapshot.activeCandidateId;
  state.selectedCurve = snapshot.selectedCurve;
  state.curveFilter = snapshot.curveFilter;
  return snapshot;
}

export function synchronizeCandidateSelectionPanels(renderers = {}, options = {}) {
  const { syncCurveScroll = false } = options;
  const {
    renderSelected = () => {},
    renderYellowReasonPanel = () => {},
    renderTable = () => {},
    draw2dMap = () => {},
    update3dSelection = () => {},
    renderTess = () => {},
    renderCurves = () => {}
  } = renderers;

  renderSelected();
  renderYellowReasonPanel();
  renderTable();
  draw2dMap();
  update3dSelection();
  renderTess();
  renderCurves(false, syncCurveScroll);

  return [...SELECTION_PANEL_KEYS];
}
