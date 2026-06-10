import { beforeEach, describe, expect, it, vi } from 'vitest';

function installDom() {
  const elements = new Map();
  global.window = { ASTRO_DASHBOARD_NOTIFICATIONS: null };
  global.document = {
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, {
          id,
          textContent: "",
          style: {},
          remove: vi.fn(),
        });
      }
      return elements.get(id);
    },
  };
  return elements;
}

async function importDataLoader() {
  vi.resetModules();
  return import('../src/dataLoader.js');
}

describe('split dashboard data loading', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    installDom();
  });

  it('reports a visible error when candidates-summary.json is missing', async () => {
    vi.stubGlobal('fetch', vi.fn(async (path) => ({
      ok: false,
      status: path === 'candidates-summary.json' ? 404 : 500,
      json: async () => ({}),
    })));
    const { data, loadData } = await importDataLoader();

    await expect(loadData()).resolves.toBe(false);

    expect(data.candidates).toEqual([]);
    expect(data.loadError?.type).toBe('SUMMARY_LOAD_FAILED');
    expect(document.getElementById('dataStatus').textContent).toContain('candidates-summary.json');
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(['candidates-summary.json']);
  });

  it('keeps the summary candidate and marks a detail error when a lazy detail file is missing', async () => {
    const summaryCandidate = {
      tic: 75878355,
      status: 'SPC_STRONG',
      evidenceScore: 96,
      detailsPath: 'candidate-details/TIC_75878355.json',
    };
    vi.stubGlobal('fetch', vi.fn(async (path) => {
      if (path === 'candidates-summary.json') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ summary: { total: 1 }, candidates: [summaryCandidate] }),
        };
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({}),
      };
    }));
    const { data, loadCandidateDetails, loadData } = await importDataLoader();

    await expect(loadData()).resolves.toBe(true);
    const result = await loadCandidateDetails(summaryCandidate);

    expect(result).toBe(data.candidates[0]);
    expect(result._detailLoadError?.type).toBe('DETAIL_LOAD_FAILED');
    expect(result.status).toBe('SPC_STRONG');
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      'candidates-summary.json',
      'candidate-details/TIC_75878355.json',
    ]);
  });
});
