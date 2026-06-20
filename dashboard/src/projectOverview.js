const de = {
  title: "Funktionsübersicht",
  subtitle: "Alle wissenschaftlichen Prüfungen, Datenprodukte und Bedienfunktionen der aktuellen Kwarves-Pipeline.",
  levelTitle: "Verarbeitungsstufen",
  checksLabel: "Prüfungen und Funktionen",
  outputsLabel: "Ergebnisse",
  areas: [
    {
      id: "targets",
      icon: "database",
      title: "1. Zielauswahl und Sternkatalog",
      summary: "Gaia- und TIC-Daten bilden die kontrollierte Ausgangsmenge für die Transit-Suche.",
      checks: ["TIC-/Gaia-Import", "Temperatur, Radius, logg und TESS-Helligkeit", "Entfernung bis 500 Lichtjahre", "K-, G- und M-Zwerg-Auswahl"],
      outputs: ["rohdaten", "kstars_active", "candidates_v2"]
    },
    {
      id: "lightcurves",
      icon: "activity",
      title: "2. TESS-Lichtkurven und Transit-Suche",
      summary: "TESS-Sektoren werden geprüft, Lichtkurven aufbereitet und mit BLS/TLS nach periodischen Signalen durchsucht.",
      checks: ["SAP-/PDCSAP-Vergleich", "Sektoren verbinden und Ausreißer entfernen", "BLS- und Spezial-TLS-Suche", "Periode, T0, Dauer, Tiefe, SNR und sichtbare Transits"],
      outputs: ["Lichtkurven-CSV", "Roh-, Folded- und Combined-PNG", "Transit-Ephemeride"]
    },
    {
      id: "hz",
      icon: "sun-medium",
      title: "3. Habitable Zone",
      summary: "Die Bestrahlungs- und Periodengrenzen werden nach Kopparapu aus den Sternparametern berechnet.",
      checks: ["Leuchtkraft und Sternmasse", "HZ-Grenzen in AU und Tagen", "KONSERVATIVE_HZ", "OPT_HZ_INNEN; ZU_HEISS wird ausgeschlossen"],
      outputs: ["hz_status", "HZ-Priorität", "HZ-Review"]
    },
    {
      id: "vetting",
      icon: "shield-check",
      title: "4. Transit-Plausibilität und False Positives",
      summary: "Mehrere unabhängige Tests trennen planetenähnliche Signale von EBs, Aktivität und Datenartefakten.",
      checks: ["Odd/Even und Secondary Eclipse", "U-/V-Shape und Shape-SNR", "Baseline und Out-of-transit-Streuung", "SAP/PDCSAP, Rotation, Alias, Datenlücken und Sektorrand"],
      outputs: ["transit_shape", "FP-/Artefakt-Flags", "folded_lc_quality", "shape_blocking_issues"]
    },
    {
      id: "catalogs",
      icon: "telescope",
      title: "5. Externe Katalogprüfung",
      summary: "Öffentliche Kataloge und Gaia-Nachbarquellen zeigen bekannte Objekte und mögliche Kontaminationen.",
      checks: ["NASA Exoplanet Archive", "TOI/ExoFOP", "Simbad", "Gaia-Nachbarsterne und Blend-Risiko"],
      outputs: ["Known/unknown Status", "Katalogtreffer", "Kontaminationshinweise"]
    },
    {
      id: "single-transits",
      icon: "scan-line",
      title: "6. Level-5-Einzeltransite",
      summary: "Jeder erwartete Transit wird einzeln vermessen; echte Level-5-Daten haben Vorrang vor Fallbacks.",
      checks: ["Lokale Tiefe und SNR", "sichtbare und robuste Events", "Depth Scatter und Depth CV", "Sektor- und Einzelereignis-Konsistenz"],
      outputs: ["Einzeltransit-Eventliste", "Depth-Stability-Metriken", "Einzeltransit-CSV und PNG"]
    },
    {
      id: "ttv",
      icon: "chart-no-axes-combined",
      title: "7. O-C, TTV und Multi-Planet Review",
      summary: "Gemessene Transitzeiten werden mit der Ephemeride verglichen; TTV ist ein Review-Signal und kein alleiniger harter Blocker.",
      checks: ["O-C pro Transit", "Timing-Unsicherheit", "Scatter und Peak-to-Peak", "POSSIBLE, STRONG oder IRREGULAR TTV"],
      outputs: ["ttvStatus", "O-C-CSV und Plot", "MULTI_SIGNAL-/MULTI_PLANET-Flags"]
    },
    {
      id: "decision",
      icon: "list-checks",
      title: "8. Evidence, SPC und VVT",
      summary: "Signal-, Daten- und Vetting-Evidenz werden zu einer nachvollziehbaren Follow-up-Entscheidung zusammengeführt.",
      checks: ["Evidence Score und Multi-Method Score", "SPC_STRONG, SPC_ART und FOLLOWUP_READY", "harte und weiche VVT-Blocker", "TTV als Review-/Science-Interest-Signal"],
      outputs: ["vvtScore", "vvtStatus", "vvtBlockingIssues", "vvtReviewNotes"]
    },
    {
      id: "persistence",
      icon: "layers-3",
      title: "9. Persistenz und Batch-Verarbeitung",
      summary: "Alle Kandidaten können sicher in Batches verarbeitet und nach Unterbrechungen fortgesetzt werden.",
      checks: ["--all-candidates und Batchgröße", "Resume und Offline-Cache", "Lightcurve-/Transit-Skip-Regeln", "gute reale Daten nicht durch schwächere Daten überschreiben"],
      outputs: ["Resume-Datei", "JSONL-/CSV-Zwischenstände", "Candidate Matrix", "Summary- und Detail-JSON"]
    },
    {
      id: "dashboard",
      icon: "layout-dashboard",
      title: "10. Dashboard und Review",
      summary: "Die Oberfläche verbindet Matrix, Kandidatendetails, Vetting, Lichtkurven, Karten und Follow-up-Listen.",
      checks: ["HZ-, SPC-, VVT- und TTV-Filter", "synchronisierte Kandidatenauswahl", "2D/3D-Sternkarte und TESS-Sektoren", "Deutsch, Englisch, Französisch und mobile Ansicht"],
      outputs: ["candidates-summary.json", "candidate-details/TIC_*.json", "VVT Shortlist", "ExoFOP Review"]
    }
  ]
};

const en = {
  title: "Feature overview",
  subtitle: "All scientific checks, data products, and dashboard capabilities in the current Kwarves pipeline.",
  levelTitle: "Processing levels",
  checksLabel: "Checks and capabilities",
  outputsLabel: "Outputs",
  areas: [
    ["targets", "database", "1. Target selection and stellar catalog", "Gaia and TIC data define the controlled input set for the transit search.", ["TIC/Gaia import", "Temperature, radius, logg, and TESS magnitude", "Distance up to 500 light-years", "K-, G-, and M-dwarf selection"], ["rohdaten", "kstars_active", "candidates_v2"]],
    ["lightcurves", "activity", "2. TESS light curves and transit search", "TESS sectors are checked, light curves prepared, and periodic signals searched with BLS/TLS.", ["SAP/PDCSAP comparison", "Sector stitching and outlier removal", "BLS and specialist TLS search", "Period, T0, duration, depth, SNR, and visible transits"], ["Light-curve CSV", "Raw, folded, and combined PNG", "Transit ephemeris"]],
    ["hz", "sun-medium", "3. Habitable zone", "Irradiation and period boundaries are calculated from stellar parameters using Kopparapu.", ["Luminosity and stellar mass", "HZ boundaries in AU and days", "KONSERVATIVE_HZ", "OPT_HZ_INNEN; ZU_HEISS is excluded"], ["hz_status", "HZ priority", "HZ review"]],
    ["vetting", "shield-check", "4. Transit plausibility and false positives", "Independent checks separate planet-like signals from EBs, activity, and data artifacts.", ["Odd/even and secondary eclipse", "U/V shape and shape SNR", "Baseline and out-of-transit scatter", "SAP/PDCSAP, rotation, aliases, gaps, and sector edges"], ["transit_shape", "FP/artifact flags", "folded_lc_quality", "shape_blocking_issues"]],
    ["catalogs", "telescope", "5. External catalog checks", "Public catalogs and Gaia neighbors expose known objects and possible contamination.", ["NASA Exoplanet Archive", "TOI/ExoFOP", "Simbad", "Gaia neighbors and blend risk"], ["Known/unknown status", "Catalog matches", "Contamination notes"]],
    ["single-transits", "scan-line", "6. Level-5 single transits", "Each expected event is measured separately; real Level-5 data takes precedence over fallbacks.", ["Local depth and SNR", "Visible and robust events", "Depth scatter and depth CV", "Sector and event consistency"], ["Single-transit event list", "Depth-stability metrics", "Single-transit CSV and PNG"]],
    ["ttv", "chart-no-axes-combined", "7. O-C, TTV, and multi-planet review", "Measured transit times are compared with the ephemeris; TTV is a review signal, not a hard blocker by itself.", ["O-C per transit", "Timing uncertainty", "Scatter and peak-to-peak", "POSSIBLE, STRONG, or IRREGULAR TTV"], ["ttvStatus", "O-C CSV and plot", "MULTI_SIGNAL/MULTI_PLANET flags"]],
    ["decision", "list-checks", "8. Evidence, SPC, and VVT", "Signal, data, and vetting evidence are combined into a traceable follow-up decision.", ["Evidence and multi-method scores", "SPC_STRONG, SPC_ART, and FOLLOWUP_READY", "Hard and soft VVT blockers", "TTV as review/science-interest signal"], ["vvtScore", "vvtStatus", "vvtBlockingIssues", "vvtReviewNotes"]],
    ["persistence", "layers-3", "9. Persistence and batch processing", "All candidates can be processed safely in batches and resumed after interruptions.", ["--all-candidates and batch size", "Resume and offline cache", "Light-curve/transit skip rules", "Never replace good real data with weaker data"], ["Resume file", "JSONL/CSV checkpoints", "Candidate Matrix", "Summary and detail JSON"]],
    ["dashboard", "layout-dashboard", "10. Dashboard and review", "The interface joins matrix, details, vetting, light curves, maps, and follow-up lists.", ["HZ, SPC, VVT, and TTV filters", "Synchronized candidate selection", "2D/3D star map and TESS sectors", "German, English, French, and mobile layout"], ["candidates-summary.json", "candidate-details/TIC_*.json", "VVT Shortlist", "ExoFOP Review"]]
  ].map(([id, icon, title, summary, checks, outputs]) => ({ id, icon, title, summary, checks, outputs }))
};

const fr = {
  title: "Vue d'ensemble des fonctions",
  subtitle: "Tous les contrôles scientifiques, produits de données et fonctions du dashboard dans la pipeline Kwarves actuelle.",
  levelTitle: "Niveaux de traitement",
  checksLabel: "Contrôles et fonctions",
  outputsLabel: "Résultats",
  areas: [
    ["targets", "database", "1. Sélection des cibles et catalogue stellaire", "Les données Gaia et TIC définissent l'ensemble contrôlé pour la recherche de transits.", ["Import TIC/Gaia", "Température, rayon, logg et magnitude TESS", "Distance jusqu'à 500 années-lumière", "Sélection des naines K, G et M"], ["rohdaten", "kstars_active", "candidates_v2"]],
    ["lightcurves", "activity", "2. Courbes TESS et recherche de transits", "Les secteurs TESS sont vérifiés, les courbes préparées et les signaux périodiques recherchés par BLS/TLS.", ["Comparaison SAP/PDCSAP", "Assemblage des secteurs et suppression des valeurs aberrantes", "Recherche BLS et TLS spécialisée", "Période, T0, durée, profondeur, SNR et transits visibles"], ["CSV de courbe", "PNG brut, plié et combiné", "Éphéméride de transit"]],
    ["hz", "sun-medium", "3. Zone habitable", "Les limites d'irradiation et de période sont calculées selon Kopparapu.", ["Luminosité et masse stellaire", "Limites HZ en AU et jours", "KONSERVATIVE_HZ", "OPT_HZ_INNEN; ZU_HEISS est exclu"], ["hz_status", "Priorité HZ", "Revue HZ"]],
    ["vetting", "shield-check", "4. Plausibilité et faux positifs", "Des contrôles indépendants séparent les signaux planétaires des binaires, de l'activité et des artefacts.", ["Odd/even et éclipse secondaire", "Forme U/V et SNR de forme", "Baseline et dispersion hors transit", "SAP/PDCSAP, rotation, alias, lacunes et bords de secteur"], ["transit_shape", "Flags FP/artefact", "folded_lc_quality", "shape_blocking_issues"]],
    ["catalogs", "telescope", "5. Catalogues externes", "Les catalogues publics et les voisins Gaia révèlent les objets connus et les contaminations possibles.", ["NASA Exoplanet Archive", "TOI/ExoFOP", "Simbad", "Voisins Gaia et risque de blend"], ["Statut connu/inconnu", "Correspondances", "Notes de contamination"]],
    ["single-transits", "scan-line", "6. Transits individuels Level 5", "Chaque événement attendu est mesuré; les vraies données Level 5 ont priorité sur les fallbacks.", ["Profondeur locale et SNR", "Événements visibles et robustes", "Depth scatter et depth CV", "Cohérence par secteur et événement"], ["Liste des événements", "Métriques de stabilité", "CSV et PNG des transits"]],
    ["ttv", "chart-no-axes-combined", "7. O-C, TTV et revue multi-planètes", "Les temps mesurés sont comparés à l'éphéméride; le TTV seul n'est pas un blocage dur.", ["O-C par transit", "Incertitude temporelle", "Dispersion et peak-to-peak", "TTV POSSIBLE, STRONG ou IRREGULAR"], ["ttvStatus", "CSV et graphique O-C", "Flags MULTI_SIGNAL/MULTI_PLANET"]],
    ["decision", "list-checks", "8. Evidence, SPC et VVT", "Les preuves de signal, de données et de vetting forment une décision de suivi traçable.", ["Evidence Score et Multi-Method Score", "SPC_STRONG, SPC_ART et FOLLOWUP_READY", "Blocages VVT durs et souples", "TTV comme signal de revue/intérêt"], ["vvtScore", "vvtStatus", "vvtBlockingIssues", "vvtReviewNotes"]],
    ["persistence", "layers-3", "9. Persistance et traitement batch", "Tous les candidats peuvent être traités par lots et repris après interruption.", ["--all-candidates et taille du lot", "Resume et cache offline", "Règles de skip courbe/transits", "Ne pas remplacer de bonnes données réelles"], ["Fichier resume", "États JSONL/CSV", "Candidate Matrix", "JSON summary et détail"]],
    ["dashboard", "layout-dashboard", "10. Dashboard et revue", "L'interface réunit matrice, détails, vetting, courbes, cartes et listes de suivi.", ["Filtres HZ, SPC, VVT et TTV", "Sélection synchronisée", "Carte 2D/3D et secteurs TESS", "Allemand, anglais, français et mobile"], ["candidates-summary.json", "candidate-details/TIC_*.json", "VVT Shortlist", "ExoFOP Review"]]
  ].map(([id, icon, title, summary, checks, outputs]) => ({ id, icon, title, summary, checks, outputs }))
};

export const projectOverviewI18n = { de, en, fr };
