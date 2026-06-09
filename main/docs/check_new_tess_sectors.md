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
  python scripts/main/check_new_tess_sectors.py --limit 100 --batch-size 20 --batch-sleep 15 --sleep 0.5 --retries 2 --retry-sleep 5

MAST-schonende Blockabfrage:
  - --batch-size legt fest, wie viele TICs in einem Block abgefragt werden.
  - --batch-sleep pausiert zwischen zwei Bloecken.
  - --sleep pausiert zwischen einzelnen TIC-Abfragen innerhalb eines Blocks.
  - --retries und --retry-sleep fangen temporaere MAST-/Netzfehler mit
    linearem Backoff ab.
  - Dieselben Werte koennen ueber Umgebungsvariablen gesetzt werden:
    KWARVES_MAST_BATCH_SIZE, KWARVES_MAST_BATCH_SLEEP,
    KWARVES_MAST_RETRIES, KWARVES_MAST_RETRY_SLEEP.

Verbesserungsbedarf:
  - Spaeter optional als automatischer Schritt in eine Wochenroutine einbauen.
  - Optional MAST-Abfrage parallelisieren, aber nur mit strengem Rate-Limit.
