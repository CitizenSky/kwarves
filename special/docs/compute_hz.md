compute_hz.py
=============

Zweck:
  Einzelwerkzeug fuer Habitable-Zone-Berechnungen nach Kopparapu et al. 2014.
  Rechnet aus Teff/Radius HZ-Grenzen in AU und Periodentage und kann Kandidaten
  aus der Datenbank gesammelt auswerten.

Wichtige Eingaben:
  - CLI: --teff, --radius, optional --period
  - oder --db fuer Datenbankmodus
  - /Users/koni/astro_projects/database/planet_hunter.db

Wichtige Ausgaben:
  - Konsolenausgabe mit konservativer/optimistischer HZ
  - ggf. DB-Auswertung je Kandidat

Abhaengigkeiten zu anderen Skripten:
  - Kein Muss in der Hauptpipeline.
  - Inhaltlich verwandt mit der HZ-Logik in masterscript_v2.py.
  - Hilfreich fuer manuelle Pruefung von HZ-Kandidaten.

Verbesserungsbedarf:
  - HZ-Logik mit masterscript_v2.py vereinheitlichen.
  - Ergebnis optional als CSV/JSON exportieren.
  - Sternmassen-Schaetzung genauer dokumentieren.

