export_all_reference_combined_plots.py
======================================

Zweck:
  Erstellt kombinierte Referenzplots fuer alle Kandidaten. Diese Plots dienen
  als visuelle Grundlage fuer manuelle Pruefung und fuer die Level-2-Auswertung.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - lokale Lichtkurven aus /Users/koni/astro_projects/lightcurves
  - Kandidaten-/Transitparameter aus der Datenbank

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level1_rohkandidaten/level1_alle_kandidaten_referenzplots
  - alle_kandidaten_referenzplots_manifest.csv

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach masterscript_v2.py, weil es Kandidaten und Lichtkurven braucht.
  - level2_planet_check.py nutzt diese Referenzplots als visuelle Artefakte.

Verbesserungsbedarf:
  - Fehlende Lichtkurven/Plots klarer protokollieren.
  - Plot-Layout und Dateinamen standardisieren.
  - Optional nur neue/geaenderte Kandidaten neu rendern.

