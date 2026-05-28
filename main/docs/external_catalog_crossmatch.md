external_catalog_crossmatch.py
==============================

Zweck:
  Vergleicht lokale Kandidaten mit externen Katalogen, vor allem NASA
  Exoplanet Archive/TOI-Informationen. Trennt neue Kandidaten von bekannten
  oder bereits katalogisierten Objekten.

Wichtige Eingaben:
  - /Users/koni/astro_projects/level2_planetencheck/level2_planetencheck_results.csv
  - externe Katalogdaten via TAP/Internet
  - optional lokale Cache-Dateien im Level-3-Ordner

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level3_externe_katalogpruefung/external_catalog_crossmatch_results.csv
  - gruppierte Plot-/Pruefordner fuer externe Kataloglage

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach level2_planet_check.py.
  - make_new_candidate_shortlist.py nutzt die Crossmatch-Ergebnisdatei.

Verbesserungsbedarf:
  - Cache-Strategie fuer externe Kataloge klarer machen.
  - Netzwerkfehler robuster behandeln.
  - Externe Quellen/Abfragedatum in Ergebnisdatei speichern.

