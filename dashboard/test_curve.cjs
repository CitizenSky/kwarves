const pw = require('playwright');
(async () => {
  const browser = await pw.chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  
  // Debug: check if lightcurveCandidates has TIC 75878355
  const info = await page.evaluate(() => {
    const tic = 75878355;
    const curve = window.ASTRO_DASHBOARD_DATA?.lightcurveCandidates?.find(c => c.tic === tic);
    const first10 = window.ASTRO_DASHBOARD_DATA?.lightcurveCandidates?.slice(0, 3).map(c => c.tic);
    const allTics = window.ASTRO_DASHBOARD_DATA?.lightcurveCandidates?.map(c => c.tic);
    return {
      foundCurve: !!curve,
      allTics: allTics?.slice(0, 10),
      totalCurves: window.ASTRO_DASHBOARD_DATA?.lightcurveCandidates?.length,
      selectedTicInitial: window.state?.selected?.tic
    };
  });
  console.log('Curve info:', JSON.stringify(info));
  
  // Click first row and check state
  const firstRow = page.locator('tr[data-tic]').first();
  const tic = await firstRow.getAttribute('data-tic');
  console.log('First row TIC before click:', tic);
  await firstRow.click();
  await page.waitForTimeout(500);
  
  // Check state after click
  const afterClick = await page.evaluate(() => {
    return {
      selectedTic: window.state?.selected?.tic,
      selectedCurveTic: window.state?.selectedCurve?.tic,
      curveTitle: document.getElementById('curveTitle')?.textContent,
      curveMeta: document.getElementById('curveMeta')?.textContent,
      activeRow: document.querySelector('tr.active-row')?.getAttribute('data-tic'),
    };
  });
  console.log('After click:', JSON.stringify(afterClick));
  
  await browser.close();
})();
