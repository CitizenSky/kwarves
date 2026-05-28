ttv_make_graphics.py
====================

Zweck:
  Erstellt Uebersichtsgrafiken aus TTV-Prioritaeten, O-C-Ergebnissen und
  Run-Summaries. Dient als visuelles Dashboard fuer die TTV-Arbeit.

Wichtige Eingaben:
  - /Users/koni/astro_projects/level4_TTV_analyse/level4_02_ttv_prioritaet/ttv_prioritaet_alle_kandidaten.csv
  - /Users/koni/astro_projects/level4_TTV_analyse/level4_04_oc_ergebnisse
  - ttv_run_summary_*.csv

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level4_TTV_analyse/level4_05_grafiken
  - Balkendiagramme, Scatterplots und Kontaktboegen

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach ttv_analyse.py.
  - Nutzt auch Prioritaetsdaten aus der Level-4/TTV-Struktur.

Verbesserungsbedarf:
  - Fehlende Eingaben klarer melden.
  - Kontaktbogen-Groessen fuer grosse Kandidatenmengen parametrisierbar machen.
  - Dateinamen/Plot-Titel einheitlich mit ttv_analyse.py halten.

