make_new_candidate_shortlist.py
===============================

Zweck:
  Erzeugt aus den extern abgeglichenen Kandidaten eine Level-3-Shortlist der
  wahrscheinlich neuen und interessanten Planetenkandidaten.

Wichtige Eingaben:
  - /Users/koni/astro_projects/level3_externe_katalogpruefung/external_catalog_crossmatch_results.csv
  - Plotpfade aus Level 1/2/3

Wichtige Ausgaben:
  - /Users/koni/astro_projects/level3_neue_planetenkandidaten
  - Shortlist-CSV und gruppierte Kandidatenordner

Abhaengigkeiten zu anderen Skripten:
  - Laeuft nach external_catalog_crossmatch.py.
  - level4_candidate_filter.py arbeitet danach mit den uebrig gebliebenen
    starken Kandidaten weiter.

Verbesserungsbedarf:
  - Scoring transparenter dokumentieren.
  - Manuelle Overrides/Kommentare in separater Datei erlauben.
  - Besserer Schutz vor fehlenden Plotpfaden.

