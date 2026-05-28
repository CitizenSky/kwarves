masterscript_v2.py
==================

Zweck:
  Zentrales Hauptskript fuer den grossen Super-Earth-/Transit-Scan. Es liest
  Zielsterne aus der SQLite-Datenbank, laedt bzw. nutzt TESS-Lichtkurven,
  fuehrt BLS-Suchen und False-Positive-Pruefungen aus, berechnet grobe
  Habitable-Zone-Informationen und schreibt Kandidaten zurueck in CSV/DB.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - Tabellen wie rohdaten/kstars_active/candidates_v2 bzw. Pipeline-Tabellen
  - /Users/koni/astro_projects/lightcurves
  - Online-Daten ueber lightkurve/MAST, falls Daten fehlen

Wichtige Ausgaben:
  - /Users/koni/astro_projects/csv/masterscript_v2_candidates.csv
  - /Users/koni/astro_projects/csv/hz_revisit_priority.csv
  - /Users/koni/astro_projects/level1_rohkandidaten/level1_auto_plots_neuer_lauf
  - Kandidaten- und Statusdaten in planet_hunter.db

Neue HZ-/SPC-Felder:
  - hz_class: ZU_HEISS / OPT_HZ_INNEN / KONSERVATIVE_HZ / ZU_KALT / UNKNOWN
  - sector_count, clean_sector_count, sector_quality_summary
  - visible_transits, spc_class, revisit_priority, next_recheck, notes

Revisit-Regel:
  HZ-Kandidaten mit weniger als drei sichtbaren Transits werden nicht mehr nur
  wegen der kleinen Transitanzahl verworfen. Wenn hz_class OPT_HZ_INNEN oder
  KONSERVATIVE_HZ ist, distance_ly <= 150, transit_snr >= 7 und mindestens ein
  sauberer Sektor vorhanden ist, wird der Kandidat als SPC-C mit
  HZ_REVISIT_CANDIDATE markiert und in hz_revisit_priority.csv priorisiert.

Abhaengigkeiten zu anderen Skripten:
  - Startpunkt der Hauptpipeline.
  - Danach sinnvoll: export_all_reference_combined_plots.py
  - Danach sinnvoll: level2_planet_check.py
  - scripts/special/compute_hz.py enthaelt aehnliche HZ-Logik als
    Einzelwerkzeug, ist aber kein direkter Import.

Verbesserungsbedarf:
  - Gemeinsame Hilfsfunktionen fuer HZ, Lightcurve-Laden und BLS auslagern.
  - Parameter/Schwellwerte in eine Config-Datei verschieben.
  - Mehr Resume-/Checkpoint-Logik fuer lange Laeufe.
  - Tests fuer Klassifikation und DB-Schreiblogik ergaenzen.
