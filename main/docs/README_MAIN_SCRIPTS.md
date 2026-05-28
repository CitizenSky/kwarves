Hauptskripte im Ordner scripts/main
===================================

Dieser Ordner enthaelt die regelmaessig wichtigen Analyse- und Betriebsskripte.
Spezialskripte liegen unter:

  /Users/koni/astro_projects/scripts/special

Archivierte oder kandidatenspezifische Einmalskripte liegen unter:

  /Users/koni/astro_projects/archive/scripts

Empfohlene Haupt-Pipeline:

  1. masterscript_v2.py
  2. export_all_reference_combined_plots.py
  3. level2_planet_check.py
  4. external_catalog_crossmatch.py
  5. make_new_candidate_shortlist.py
  6. level4_candidate_filter.py
  7. evidence_vetting.py
  8. advanced_bayesian_vetting.py  (nur SPCs / starke Kandidaten / HZ-Ziele)
  9. ttv_analyse.py
  10. ttv_make_graphics.py

Optionale regelmaessige Vorpruefung:

  - check_new_tess_sectors.py
    Prueft, ob fuer bekannte Kandidaten neue TESS-Sektoren verfuegbar sind.
    Markiert solche Faelle als RECHECK_NEW_SECTOR, damit masterscript_v2.py
    sie erneut scannt.

Betriebsskripte:

  - check_new_tess_sectors.py
  - sync_astro_to_icloud.sh

Die Dokumentation liegt getrennt von den Skripten in:

  /Users/koni/astro_projects/scripts/main/docs

Zu jedem Skript gibt es dort eine gleichnamige .md-Datei mit Zweck,
Abhaengigkeiten, Ausgaben und Verbesserungsbedarf.
