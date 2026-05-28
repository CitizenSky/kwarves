level2_planet_check.py
======================

Zweck:
  Prueft rohe Kandidaten auf Planet-Plausibilitaet. Bewertet Signalform,
  Streuung, Tiefe, SNR, HZ-Status und False-Positive-Hinweise und sortiert
  Kandidaten in Level-2-Kategorien.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - /Users/koni/astro_projects/lightcurves
  - Referenzplots aus level1_alle_kandidaten_referenzplots

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level2_planetencheck/level2_planetencheck_results.csv
  - sortierte Level-2-Unterordner mit Plot-Links/Kopien

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach masterscript_v2.py und idealerweise nach
    export_all_reference_combined_plots.py.
  - external_catalog_crossmatch.py nutzt level2_planetencheck_results.csv.

Verbesserungsbedarf:
  - Bewertungsregeln als Konfigurationsblock dokumentieren.
  - Unsichere Kandidaten mit konkreten naechsten Checks markieren.
  - Tests fuer classify()/measure_shape() ergaenzen.

