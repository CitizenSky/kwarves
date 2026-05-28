evidence_vetting.py
===================

Zweck:
  Neue Evidence-Schicht nach masterscript_v2.py. Das Skript bewertet jeden
  Kandidaten mit erklaerbaren 0-100 Scores, Flags und einer Kandidatenklasse.
  Es fuehrt keine GP-, MCMC- oder Bayes-Fits aus und bleibt damit deutlich
  schneller als die Slow-Science-Stufe.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - Tabelle candidates_v2
  - /Users/koni/astro_projects/lightcurves/TIC_*/TIC_*_lightcurve.csv
  - optional eine Kandidaten-CSV via --input-csv

Scores:
  - evidence_score
  - data_window_score
  - transit_stability_score
  - sap_pdcsap_score
  - odd_even_score
  - activity_score
  - followup_score
  - scientific_value_score

Kandidatenklassen:
  - SPC_STRONG
  - SPC_WEAK_DATA
  - SPC_ACTIVE_STAR
  - SPC_FOLLOWUP_READY
  - SPC_RV_NEEDED
  - SPC_ART
  - EB_RISK
  - REJECTED
  - NEEDS_MORE_TESS_DATA

Wichtige Ausgaben:
  Jeder Lauf bekommt einen neuen Timestamp-Ordner unter:

    /Users/koni/astro_projects/evidence_vetting/YYYYMMDD_HHMMSS_evidence_vetting

  Darin:
  - evidence_vetting_results.csv
  - data_window_quality.csv
  - transit_events.csv
  - followup_priority.csv
  - advanced_bayesian_input.csv
  - candidate_dashboard.html
  - run.log

DB-Ausgabe:
  - evidence_vetting_results

Beispiele:
  python3 /Users/koni/astro_projects/scripts/main/evidence_vetting.py --max-candidates 50
  python3 /Users/koni/astro_projects/scripts/main/evidence_vetting.py --tic 261107297
  python3 /Users/koni/astro_projects/scripts/main/evidence_vetting.py --input-csv /path/to/candidates.csv --dry-run

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach masterscript_v2.py.
  - advanced_bayesian_input.csv ist der direkte Eingang fuer
    advanced_bayesian_vetting.py.

Hinweise:
  - Fehlende SAP/PDCSAP-Spalten werden als SAP_PDCSAP_UNAVAILABLE markiert und
    nicht hart verworfen.
  - Follow-up-Zeiten werden als BTJD und, wenn astropy.time verfuegbar ist, als
    UTC ausgegeben.
  - Die HTML-Datei ist ein statischer Review-Export, kein Server-Dashboard.
