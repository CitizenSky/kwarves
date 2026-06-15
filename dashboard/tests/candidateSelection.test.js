import { describe, expect, it, vi } from 'vitest';
import {
  SELECTION_PANEL_KEYS,
  applyCandidateSelectionSnapshot,
  createCandidateSelectionSnapshot,
  synchronizeCandidateSelectionPanels
} from '../src/logic/candidateSelection.js';

function makeCandidate(overrides = {}) {
  return {
    tic: 75878355,
    status: 'SPC',
    lightcurveImg: 'lightcurves/TIC_75878355.png',
    ...overrides
  };
}

describe('candidate selection state', () => {
  it('uses lazy detail data as the central selected candidate', () => {
    const summary = makeCandidate({ status: 'SUMMARY_ONLY' });
    const detail = makeCandidate({ status: 'DETAIL_LOADED', evidenceScore: 96 });
    const curve = { tic: 75878355, lightcurveImg: 'lightcurves/TIC_75878355.png' };

    const snapshot = createCandidateSelectionSnapshot(summary, {
      detailedCandidate: detail,
      currentCurveFilter: 'green',
      curveForCandidate: (candidate) => candidate.tic === curve.tic ? curve : null,
      curveMatchesFilter: () => false
    });

    expect(snapshot.selectedCandidate).toBe(detail);
    expect(snapshot.activeCandidateId).toBe(75878355);
    expect(snapshot.selectedCurve).toBe(curve);
    expect(snapshot.curveFilter).toBe('all');
    expect(snapshot.resetCurveFilter).toBe(true);
    expect(snapshot.panels).toEqual(SELECTION_PANEL_KEYS);
  });

  it('clears stale light curve state when the selected candidate has no curve', () => {
    const state = {
      selected: null,
      selectedCandidate: null,
      activeCandidateId: null,
      selectedCurve: { tic: 1, lightcurveImg: 'old.png' },
      curveFilter: 'all'
    };
    const candidate = makeCandidate({ tic: 239187696, lightcurveImg: '' });
    const snapshot = createCandidateSelectionSnapshot(candidate, {
      curveForCandidate: () => null
    });

    applyCandidateSelectionSnapshot(state, snapshot);

    expect(state.selectedCandidate).toBe(candidate);
    expect(state.activeCandidateId).toBe(239187696);
    expect(state.selectedCurve).toBeNull();
  });
});

describe('candidate selection panel synchronization', () => {
  it('updates candidate summary, vetting, blocking, multi-method, light curve, and matrix panels together', () => {
    const calls = [];
    const makeRenderer = (name) => vi.fn(() => calls.push(name));
    const renderers = {
      renderSelected: makeRenderer('candidate-summary/vetting/blocking/multi-method'),
      renderYellowReasonPanel: makeRenderer('blocking-issues-context'),
      renderTable: makeRenderer('matrix-selection'),
      draw2dMap: makeRenderer('star-map-selection'),
      update3dSelection: makeRenderer('3d-map-selection'),
      renderTess: makeRenderer('transit-panels'),
      renderCurves: vi.fn((reset, syncScroll) => calls.push(`light-curve:${reset}:${syncScroll}`))
    };

    const panels = synchronizeCandidateSelectionPanels(renderers, { syncCurveScroll: true });

    expect(panels).toEqual([
      'candidateSummary',
      'vettingProgressTree',
      'blockingIssues',
      'multiMethodEvidence',
      'lightCurve',
      'matrixSelection',
      'starMap',
      'tessCoverage'
    ]);
    expect(calls).toEqual([
      'candidate-summary/vetting/blocking/multi-method',
      'blocking-issues-context',
      'matrix-selection',
      'star-map-selection',
      '3d-map-selection',
      'transit-panels',
      'light-curve:false:true'
    ]);
    expect(renderers.renderCurves).toHaveBeenCalledWith(false, true);
  });
});

