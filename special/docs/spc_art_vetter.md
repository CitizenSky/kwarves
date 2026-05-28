spc_art_vetter.py
=================

Zweck:
  Einzelkandidaten-Vetter fuer starke oder strittige Kandidaten. Laedt und
  analysiert Lichtkurven, prueft Rotation, BLS/TLS-Signale, Odd/Even,
  Sekundaerereignisse und Aperture-/Pixel-Informationen.

Wichtige Eingaben:
  - CLI-Parameter wie --tic, --period, --duration, optional --sectors
  - TESS/lightkurve/MAST-Daten
  - optional vorhandene lokale Review-Ordner

Wichtige Ausgaben:
  - TIC-spezifische Review-Ordner unter /Users/koni/astro_projects/level4_TTV_analyse
  - Plots, JSON/Reports und Diagnoseartefakte

Abhaengigkeiten zu anderen Skripten:
  - Wird meist nach level4_candidate_filter.py fuer einzelne Kandidaten genutzt.
  - Kann Befunde liefern, die spaeter manuell in DB/Level-Ordner einfliessen.
  - Kein direkter Import durch die Hauptpipeline.

Verbesserungsbedarf:
  - Output-Format staerker standardisieren.
  - Ergebnisse optional direkt als Level-4-kompatibles CSV/JSON exportieren.
  - Download-/Cache-Verhalten dokumentieren.

