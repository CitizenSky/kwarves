check_new_tess_sectors.py
=========================

Zweck:
  Prueft bekannte Kandidaten bei MAST/lightkurve auf neu verfuegbare TESS-
  Sektoren. Wenn neue Sektoren gefunden werden, wird der Kandidat als
  RECHECK_NEW_SECTOR markiert, damit masterscript_v2.py ihn erneut scannt.

Wichtige Eingaben:
  - /Users/koni/astro_projects/database/planet_hunter.db
  - Kandidaten aus candidates_v2
  - Online-Abfrage via lightkurve/search_lightcurve

Wichtige Ausgaben:
  - Neue DB-Tabelle tess_sector_inventory
  - Status RECHECK_NEW_SECTOR in candidates_v2, rohdaten und kstars_active,
  sofern neue Sektoren gefunden wurden und der Kandidat kein FP, FP_ART oder
  FALSE_POSITIVE ist. SPC-A/SPC-B/SPC-C werden dabei mitverfolgt.

Abhaengigkeiten zu anderen Skripten:
  - Laeuft vor masterscript_v2.py, wenn man gezielt neue Sektoren nachziehen
    will.
  - masterscript_v2.py scannt RECHECK_NEW_SECTOR wie RECHECK.

Typische Nutzung:
  python scripts/main/check_new_tess_sectors.py --limit 50
  python scripts/main/check_new_tess_sectors.py --tic 13096842
  python scripts/main/check_new_tess_sectors.py --dry-run --limit 20

Verbesserungsbedarf:
  - Spaeter optional als automatischer Schritt in eine Wochenroutine einbauen.
  - Bei sehr vielen Kandidaten Batch-/Cache-Strategie optimieren.
  - Optional MAST-Abfrage parallelisieren, aber mit Rate-Limit.
