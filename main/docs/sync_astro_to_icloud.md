sync_astro_to_icloud.sh
=======================

Zweck:
  Synchronisiert /Users/koni/astro_projects nach iCloud Drive unter
  astro_projects. Wird automatisch per LaunchAgent taeglich um 21:00 Uhr
  gestartet und kann manuell mit --dry-run oder --delete ausgefuehrt werden.

Wichtige Eingaben:
  - lokaler Projektordner /Users/koni/astro_projects
  - iCloud-Zielordner ~/Library/Mobile Documents/com~apple~CloudDocs/astro_projects

Wichtige Ausgaben:
  - aktualisierte iCloud-Sync-Kopie
  - Logs unter /Users/koni/astro_projects/logs

Abhaengigkeiten zu anderen Skripten:
  - Betriebsskript, keine Analyse-Abhaengigkeit.
  - LaunchAgent:
    /Users/koni/Library/LaunchAgents/com.koni.astro-icloud-sync.plist
  - Wichtig: lightcurves/ ist ausgeschlossen, damit iCloud nicht wieder mit
    ca. 13 GB Lichtkurven gefuellt wird.

Verbesserungsbedarf:
  - Optional bessere Log-Rotation.
  - Optional --itemize-changes fuer aussagekraeftigere Dry-Runs.
  - Optional Warnung, wenn iCloud nicht erreichbar ist.

