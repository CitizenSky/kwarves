level4_candidate_filter.py
==========================

Zweck:
  Tiefer Kandidatenfilter. Prueft Einzeltransits, Odd/Even, Secondary Eclipse,
  Zeitsegmente/Sektoren, externe Kataloglage und optional Gaia/Simbad-Naehe.
  Kann Ergebnisse in CSV/DB schreiben und mit --apply-status Statusfelder
  direkt aktualisieren.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - /Users/koni/astro_projects/lightcurves
  - Level-3-Katalogcache und externe Katalogdaten

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level4_TTV_analyse/level4_06_level4_filter
  - level4_filter_results.csv
  - DB-Tabelle level4_filter_results
  - optional Status-Updates in candidates_v2/rohdaten/kstars_active

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach Level-2/Level-3-Pipeline.
  - Ergebnisse bestimmen, welche Kandidaten spaeter mit ttv_analyse.py oder
    scripts/special/spc_art_vetter.py tiefer betrachtet werden.

Verbesserungsbedarf:
  - Sehr gross: gemeinsame Module fuer TAP-Abfragen, Lightcurve-Laden und
    Transitmetriken waeren sinnvoll.
  - --apply-status sollte vor jedem DB-Write automatisch ein Backup anlegen.
  - Ergebnisgruende noch maschinenlesbarer machen.
