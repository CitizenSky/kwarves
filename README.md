# CitizenSky / Kwarves

Independent citizen-science dashboard for screening nearby exoplanet candidates from public TESS and Gaia data.

## Live Dashboard

- https://citizensky.github.io/kwarves/dashboard/

## Project Summary

CitizenSky/Kwarves analyzes publicly available TESS, Gaia DR3, and TIC data to organize nearby stellar targets, inspect transit-like signals, and prioritize candidates for recheck or follow-up. The dashboard focuses on K-dwarf systems, habitable-zone context, SPC/SPC_ART classifications, and follow-up priority.

The public dashboard includes candidate status, evidence scores, TESS sector/recheck information, light-curve previews, matrix statistics, and project methodology notes.

## Data Sources

- TESS / MAST light curves and sector products
- Gaia DR3 stellar parameters and astrometry
- TIC target identifiers and catalog metadata

## Disclaimer

CitizenSky/Kwarves is an independent citizen-science project. Results are preliminary automated screenings based on public data. Candidate classifications are not confirmed planets and require manual vetting, additional data, and professional follow-up.

## Keywords

TESS, Gaia DR3, TIC, exoplanet candidates, habitable zone, K-dwarfs, citizen science, BLS, TLS, follow-up priority.

## Deployment

This repository is deployed with GitHub Pages from the `main` branch root. The root `index.html` redirects to `dashboard/index.html`.
