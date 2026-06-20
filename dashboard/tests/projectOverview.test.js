import { describe, expect, it } from 'vitest';
import { projectOverviewI18n } from '../src/projectOverview.js';
import { projectScripts } from '../src/i18n.js';

describe('project feature overview', () => {
  it.each(['de', 'en', 'fr'])('provides the complete overview in %s', (language) => {
    const overview = projectOverviewI18n[language];

    expect(overview.title).toBeTruthy();
    expect(overview.subtitle).toBeTruthy();
    expect(overview.levelTitle).toBeTruthy();
    expect(overview.areas).toHaveLength(10);
    expect(new Set(overview.areas.map((area) => area.id))).toEqual(new Set([
      'targets', 'lightcurves', 'hz', 'vetting', 'catalogs',
      'single-transits', 'ttv', 'decision', 'persistence', 'dashboard'
    ]));
    overview.areas.forEach((area) => {
      expect(area.checks.length).toBeGreaterThanOrEqual(4);
      expect(area.outputs.length).toBeGreaterThanOrEqual(3);
    });
  });

  it('documents the resumable all-candidate batch runner', () => {
    expect(projectScripts.some((item) => item.script === 'main/run_batch_vetting_pipeline.py')).toBe(true);
  });
});
