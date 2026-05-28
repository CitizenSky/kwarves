tic13096842_analysis.py
=======================

Zweck:
  Zentraler Starter fuer die archivierten Spezialanalysen zu TIC 13096842.
  Er ersetzt nicht die alten Skripte, sondern ruft sie aus dem Archiv heraus
  mit klaren Subcommands auf.

Wichtige Eingaben:
  - archivierte Skripte unter archive/scripts/2026-05-21_cleanup/tic13096842
  - /Users/koni/astro_projects/lightcurves/TIC_13096842
  - Level-6-Dossierdaten fuer TIC 13096842

Wichtige Ausgaben:
  - Outputs der jeweiligen Archivskripte im Level-6-Dossier
  - Sector-98-Reanalyse, Fits, TTV-Fokus, Resonanzsuche, Confirmation-Checks

Abhaengigkeiten zu anderen Skripten:
  - Nutzt tic13096842_sector98.py fuer alle Sector-98-Schritte.
  - Wrapper fuer archivierte TIC-13096842-Skripte.
  - Fuer normale Pipeline nicht erforderlich.
  - Nutzt Ergebnisse/Dateien, die historisch aus ttv_analyse.py und
    Sector-98-Spezialanalysen entstanden sind.

Verbesserungsbedarf:
  - Langfristig die archivierten Einzeldateien zu einem echten Modul
    zusammenfassen.
  - Gemeinsame Parameter wie TIC, Sektor, Output-Basis konfigurierbar machen.
