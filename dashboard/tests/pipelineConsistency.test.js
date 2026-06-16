import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { describe, expect, it } from 'vitest';

const dashboardRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const projectRoot = path.resolve(dashboardRoot, '../..');
const matrixCsvPath = path.join(projectRoot, 'candidate_matrix/candidate_matrix.csv');

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(dashboardRoot, relativePath), 'utf8'));
}

function parseCsvLine(line) {
  const fields = [];
  let current = '';
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      fields.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  fields.push(current);
  return fields;
}

function readCandidateMatrixRow(tic) {
  const lines = fs.readFileSync(matrixCsvPath, 'utf8').trimEnd().split(/\r?\n/);
  const headers = parseCsvLine(lines[0]);
  const ticIndex = headers.indexOf('tic_id');
  const line = lines.find((row, index) => index > 0 && parseCsvLine(row)[ticIndex] === String(tic));
  if (!line) return null;
  return Object.fromEntries(headers.map((header, index) => [header, parseCsvLine(line)[index]]));
}

function resolveDashboardRelativePath(relativePath) {
  return path.resolve(dashboardRoot, relativePath);
}

function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

describe('pipeline end-to-end consistency', () => {
  it('keeps Candidate Matrix source fields required by dashboard vetting', () => {
    const header = parseCsvLine(fs.readFileSync(matrixCsvPath, 'utf8').split(/\r?\n/, 1)[0]);
    const requiredHeaders = [
      'tic_id',
      'evidence_score',
      'hz_status',
      'source_spc_class',
      'snr',
      'visible_transits',
      'distance_ly',
      'status',
      'status_color',
      'extended_class',
      'score_interpretation',
      'individual_transit_count',
      'visible_transit_count',
      'robust_transit_count',
      'depth_scatter_ppt',
      'median_single_transit_snr',
      'individual_transit_plot_path',
      'individual_transit_statistics_json',
      'individual_transit_events_json',
    ];

    expect(header).toEqual(expect.arrayContaining(requiredHeaders));

    const row = readCandidateMatrixRow(75878355);
    expect(row).toMatchObject({
      tic_id: '75878355',
      hz_status: 'ZU_HEISS',
      source_spc_class: 'SPC-A',
      status: 'SPC',
      status_color: 'GREEN',
      extended_class: 'SPC_STRONG',
    });
    expect(Number(row.evidence_score)).toBeGreaterThanOrEqual(90);
    expect(Number(row.snr)).toBeGreaterThan(10);
    expect(Number(row.visible_transits)).toBeGreaterThanOrEqual(3);
    expect(Number(row.distance_ly)).toBeGreaterThan(0);
  });

  it('persists real Level-5 single-transit data and keeps synthetic fallback disabled', () => {
    const expected = [
      { tic: 75878355, events: 86, visible: 12, robust: 12 },
      { tic: 239187696, events: 625, visible: 41, robust: 37 },
    ];

    for (const { tic, events, visible, robust } of expected) {
      const detail = readJson(`candidate-details/TIC_${tic}.json`);
      const stats = detail.individualTransitStatistics;

      expect(stats.source).toBe('LEVEL5_SINGLE_TRANSITS');
      expect(stats.csvAvailable).toBe(true);
      expect(stats.individualTransitCount).toBe(events);
      expect(stats.visibleTransitCount).toBe(visible);
      expect(stats.robustTransitCount).toBe(robust);
      expect(Number(stats.depthScatterPpt)).toBeGreaterThanOrEqual(0);
      expect(Number(stats.medianSingleTransitSnr)).toBeGreaterThan(0);
      expect(stats.individualTransitPlotPath).toContain(`TIC_${tic}_single_transits.png`);
      expect(fs.existsSync(resolveDashboardRelativePath(stats.individualTransitPlotPath))).toBe(true);

      expect(detail.individualTransitEvents).toHaveLength(events);
      expect(detail.individualTransitEvents.filter((event) => event.visible)).toHaveLength(visible);
      expect(detail.individualTransitPlotPath).toBe(stats.individualTransitPlotPath);
      expect(detail.stage2FallbackUsed).toBe(false);
      expect(String(detail.stage2ComputationStatus || '')).not.toContain('RUNTIME_FALLBACK');
    }
  });

  it('exports VVT fields and treats TTV as review signal instead of hard blocker', () => {
    const detail = readJson('candidate-details/TIC_239187696.json');

    expect(detail).toEqual(expect.objectContaining({
      vvtScore: expect.any(Number),
      vvtStatus: expect.stringMatching(/^(EXOFOP_READY|NEEDS_REVIEW|BLOCKED|WAIT_FOR_DATA)$/),
      vvtBlockingIssues: expect.any(Array),
      vvtReviewNotes: expect.any(Array),
    }));
    expect(detail.ttvStatus).toBe('TIMING_OR_DEPTH_SCATTER_RISK');
    expect(detail.vvtBlockingIssues.join(' ')).not.toMatch(/TTV|TIMING|SCATTER/i);
    expect(detail.vvtReviewNotes.join(' ')).toMatch(/manual timing review/i);
    expect(detail.vvtReviewNotes.join(' ')).toMatch(/not a hard blocker/i);
  });

  it('keeps summary records lightweight and full vetting data in lazy detail records', () => {
    const summary = readJson('candidates-summary.json');
    const summaryCandidate = summary.candidates.find((candidate) => candidate.tic === 75878355);
    const detail = readJson('candidate-details/TIC_75878355.json');

    expect(summaryCandidate).toBeTruthy();
    expect(summaryCandidate.detailsPath).toBe('candidate-details/TIC_75878355.json');
    expect(summaryCandidate).toEqual(expect.objectContaining({
      tic: 75878355,
      evidenceScore: expect.any(Number),
      hz: expect.any(String),
      snr: expect.any(Number),
      visibleTransits: expect.any(Number),
      distance: expect.any(Number),
      status: expect.any(String),
      matrixClass: expect.any(String),
      displayLabels: expect.any(Array),
      vvtScore: expect.any(Number),
      vvtStatus: expect.any(String),
    }));

    const heavyFields = [
      'individualTransitEvents',
      'individualTransitStatistics',
      'foldedLightCurveShape',
      'methodEvidenceFlags',
      'astroMonitor',
      'fullVetting',
      'spcArtStage2',
    ];
    for (const field of heavyFields) {
      expect(summaryCandidate).not.toHaveProperty(field);
      expect(detail).toHaveProperty(field);
    }
  });

  it('keeps dashboard light curves matched to their candidate TICs', () => {
    const summary = readJson('candidates-summary.json');
    const referencedDeployFiles = new Set();

    for (const candidate of summary.candidates) {
      const detail = readJson(`candidate-details/TIC_${candidate.tic}.json`);
      const deployPath = detail.lightcurveImgDeploy || detail.lightcurveImg;
      const localPath = detail.lightcurveImgLocal;

      expect(candidate.lightcurveImg).toBe(`lightcurves/TIC_${candidate.tic}.png`);
      expect(detail.lightcurveImg).toBe(`lightcurves/TIC_${candidate.tic}.png`);
      expect(deployPath).toBe(`lightcurves/TIC_${candidate.tic}.png`);
      expect(localPath).toContain(`TIC_${candidate.tic}/`);

      const deployFullPath = resolveDashboardRelativePath(deployPath);
      const localFullPath = resolveDashboardRelativePath(localPath);
      expect(fs.existsSync(deployFullPath)).toBe(true);
      expect(fs.existsSync(localFullPath)).toBe(true);
      expect(sha256(deployFullPath)).toBe(sha256(localFullPath));

      expect(referencedDeployFiles.has(path.basename(deployPath))).toBe(false);
      referencedDeployFiles.add(path.basename(deployPath));
    }

    const deployedLightcurves = fs.readdirSync(path.join(dashboardRoot, 'lightcurves'))
      .filter((fileName) => /^TIC_\d+\.png$/.test(fileName));
    expect(deployedLightcurves.sort()).toEqual([...referencedDeployFiles].sort());
  });

  it('serves a root deployment that points to an existing current bundle', () => {
    const indexHtml = fs.readFileSync(path.join(dashboardRoot, 'index.html'), 'utf8');
    const scriptMatch = indexHtml.match(/<script type="module" crossorigin src="\.\/(assets\/[^"]+\.js)"><\/script>/);
    const stylesheetMatch = indexHtml.match(/<link rel="stylesheet" crossorigin href="\.\/(assets\/[^"]+\.css)">/);

    expect(scriptMatch?.[1]).toBeTruthy();
    expect(stylesheetMatch?.[1]).toBeTruthy();
    expect(fs.existsSync(path.join(dashboardRoot, scriptMatch[1]))).toBe(true);
    expect(fs.existsSync(path.join(dashboardRoot, stylesheetMatch[1]))).toBe(true);
    expect(indexHtml.match(/data-color-filter="/g)).toHaveLength(7);
    expect(indexHtml).toContain('data-color-filter="spc-prep"');
    expect(indexHtml).toContain('data-color-filter="vvt"');
  });
});
