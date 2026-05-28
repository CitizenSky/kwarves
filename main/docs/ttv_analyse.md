ttv_analyse.py
==============

Zweck:
  Misst Transit Timing Variations fuer Kandidaten. Erstellt pro Kandidat
  O-C-Messungen, Timing-Unsicherheiten, Klassifikation der Messpunkte und
  O-C-Plots.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - /Users/koni/astro_projects/lightcurves
  - Kandidatenprioritaeten bzw. DB-Felder

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level4_TTV_analyse/level4_04_oc_ergebnisse
  - TIC-spezifische O-C CSVs und PNGs
  - ttv_run_summary_*.csv

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach Kandidatenfilterung, meist nach level4_candidate_filter.py.
  - ttv_make_graphics.py nutzt die erzeugten O-C-Ergebnisse und Summaries.
  - scripts/special/tic13096842_analysis.py nutzt archivierte Spezialvarianten
    fuer einen einzelnen Kandidaten.

Verbesserungsbedarf:
  - Bessere automatische Erkennung schlechter Einzeltransits.
  - Gemeinsame Transitfenster-Logik mit level4_candidate_filter.py teilen.
  - Mehr Schutz gegen Alias-/Periodenfehler.
