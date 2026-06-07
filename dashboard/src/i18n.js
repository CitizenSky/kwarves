import { state, SUPPORTED_LANGS, LANGUAGE_KEY, LANGUAGE_LOCALES, tessMission } from './state.js';

export const I18N = {
  de: {
    app_title: "CitizenSky \u2013 Exoplanet Candidate Dashboard",
    nav_kandidaten: "Kandidaten",
    nav_analyse: "Analyse",
    nav_tess: "TESS",
    nav_projekt: "Projekt",
    about_project_title: "Ueber CitizenSky / Methodik",
    lang_switch_label: "Sprache",
    nav_tree: "Baumstruktur",
    nav_map: "Sternkarte",
    nav_tess: "TESS",
    nav_curves: "Lichtkurven",
    nav_table: "Kandidaten",
    nav_docs: "Projektlogik",
    nav_impressum: "Impressum",
    nav_admin: "ExoFOP Review",
    sidebar_rule_title: "Leseregel",
    sidebar_rule_text: "Violett ist ein Zusatzmarker fuer HZ/Top-Tier. Ein Kandidat kann also gruen und violett sein.",
    refresh_data: "Daten neu bauen",
    search_placeholder: "Suche: TIC, Farbe, HZ, Status",
    hint_button_title: "Hinweise",
    notifications_title: "Dashboard Hinweise",
    notifications_empty: "Keine neuen Neubewertungen im letzten automatischen Lauf.",
    notifications_summary: "{total} Hinweise aus dem letzten automatischen Lauf. LIVE_NOW: {live}, UPCOMING: {upcoming}, WAITING_DATA: {waiting}.",
    notifications_updated: "Aktualisiert: {date}",
    notification_change_count: "{count} Bewertungsfelder geaendert",
    notification_new_sectors: "Neue Sektoren: {sectors}",
    notification_recheck_line: "Recheck: {status} \u00b7 aktueller Sektor: {current} \u00b7 naechster Plan: {next} \u00b7 Daten ca.: {date}",
    toast_notifications: "{count} Dashboard-Hinweise geoeffnet.",
    hz_focus: "HZ Fokus",
    lede: "Analyse echter TESS-Daten mit Farbklassifikation, Lichtkurven-Vetting und interaktiver Sternkarte.",
    kpi_total: "Alle Kandidaten",
    kpi_total_sub: "aus Manifest",
    kpi_green: "Gruen",
    kpi_green_sub: "SPC-Kandidaten",
    kpi_yellow: "Orange",
    kpi_yellow_sub: "normales Recheck-Orange",
    kpi_spc_prep: "SPC Prep",
    kpi_spc_prep_sub: "gelb markiert",
    kpi_red: "Rot",
    kpi_red_sub: "FP/Systematik",
    kpi_violet: "Violett",
    kpi_violet_sub: "HZ/Top-Tier",
    filter_all: "Alle",
    filter_green: "Gruen",
    filter_yellow: "Orange",
    filter_spc_prep: "SPC Prep",
    filter_red: "Rot",
    filter_violet: "Violett",
    curves_filter_all: "Alle",
    curves_filter_green: "Gruen",
    curves_filter_spc_prep: "Gelb",
    curves_filter_orange: "Orange",
    curves_filter_red: "Rot",
    curves_filter_violet: "Lila",
    map_legend_green: "Gruen = Kandidat",
    map_legend_yellow: "Orange = in Pruefung",
    map_legend_spc_prep: "Gelb = SPC Prep",
    map_legend_red: "Rot = FP/Rejected",
    map_legend_violet: "Violett-Ring = HZ-Fokus",
    map_legend_selected: "Weisser Ring = ausgewaehlt",
    map_legend_sun: "Sonne/Erde (Standpunkt)",
    map_notice_symbolic: "Vereinfachte Sternkarten-Planungsansicht. Positionen, Winkel und Abstaende sind symbolisch und nicht astronomisch masstabsgetreu.",
    map_notice_gaia_full: "Astrometrische Himmelskarte auf Gaia-Basis (RA/Dec) fuer alle {total} Kandidaten. Winkel/Anordnung sind astronomisch, die Radialtiefe ist fuer die Visualisierung skaliert.",
    map_notice_gaia_mixed: "Gemischte Karte: {gaia} Kandidaten mit Gaia-RA/Dec ({pct}%), {fallback} noch als Heuristik. Winkel sind nur fuer Gaia-Punkte astronomisch korrekt.",
    tess_notice_symbolic: "Vereinfachte TESS-Planungsansicht. Positionen, Winkel und Abstaende sind symbolisch und nicht astronomisch masstabsgetreu.",
    timeline_title: "TESS Coverage Timeline",
    timeline_observed: "Bisher beobachtet",
    timeline_planned: "Geplant",
    timeline_next: "Naechste Beobachtung",
    timeline_status: "Status",
    selected_title: "Ausgewaehlter Kandidat",
    selected_subtitle: "Hier steht die Begruendung in Klartext.",
    chip_violet_hz: "Violett / HZ",
    chip_matrix_prefix: "Matrix {value}",
    chip_evidence_prefix: "Evidence {value}",
    chip_curve_available: "Lichtkurve vorhanden",
    detail_matrix_status: "Matrix Status",
    detail_matrix_class: "Matrix Klasse",
    detail_evidence_score: "Evidence Score",
    detail_distance: "Distanz",
    detail_period: "Periode",
    detail_snr: "SNR",
    detail_transits_visible: "Transits sichtbar",
    detail_matrix_transits: "Matrix Transits/Sektoren",
    detail_radius: "Radius",
    detail_status: "Status",
    detail_shape: "Transitform",
    detail_sap_pdcsap: "SAP vs PDCSAP",
    detail_oddeven: "Odd/Even",
    detail_secondary: "Secondary Eclipse",
    detail_depth: "Tiefe",
    detail_duration: "Dauer",
    detail_depth_stable: "Tiefe stabil?",
    detail_data_gap: "Datenluecken-Risiko",
    detail_sector_edge: "Sektorrand-Risiko",
    detail_alias: "Period-Alias-Risiko",
    detail_rotation: "Aktivitaets-Risiko",
    detail_ra: "RA",
    detail_dec: "Dec",
    detail_map_source: "Koordinatenquelle",
    map_source_gaia: "Gaia DR3/DR2 (astrometrisch)",
    map_source_fallback: "Heuristik (ohne RA/Dec)",
    matrix_reason_label: "Matrix Begruendung",
    matrix_next_label: "Naechster Schritt",
    path_prefix: "Pfad",
    footer_alert: "\u26a0\ufe0f Vorlaeufige Forschungsergebnisse. Kandidatenbewertungen koennen sich durch neue TESS-Daten, Follow-up-Beobachtungen oder externe Analysen aendern.",
    footer_about: "About",
    footer_impressum: "Impressum",
    footer_privacy: "Privacy",
    footer_github: "GitHub",
    toggle_expand: "Bereich aufklappen",
    toggle_collapse: "Bereich zuklappen",
    tess_compare_expand: "3D TESS-Sektorenkarte aufklappen",
    tess_compare_collapse: "3D TESS-Sektorenkarte einklappen",
    phase_completed: "Abgeschlossen",
    phase_planned: "Geplant",
    phase_running: "Laufend",
    unknown: "unbekannt",
    not_available: "nicht verfuegbar",
    not_set: "nicht gesetzt",
    no_entries: "Noch keine Eintraege.",
    table_empty_search: "Keine Kandidaten fuer diese Suche.",
    table_count_label: "Kandidaten",
    table_empty_filter: "Keine Kandidaten im aktuellen Filter.",
    top_candidates_empty: "Aktuell keine oeffentlich freigegebenen ExoFOP-/SPC-Kandidaten. Interne Prep-Faelle liegen im Admin-Bereich.",
    followup_candidates_empty: "Keine Follow-up-Kandidaten.",
    followup_expand: "Follow-up ausklappen",
    followup_collapse: "Follow-up einklappen",
    no_yellow_reason_tags: "Keine gelben Reason Tags.",
    no_next_check: "Kein naechster Check gesetzt.",
    yellow_summary_default: "Gelb: wissenschaftlich interessant, aber nicht sauber genug fuer automatisches Gruen",
    yellow_summary_not_yellow: "Dieser Kandidat ist aktuell nicht gelb markiert.",
    why_label: "Warum?",
    followup_label: "Follow-up",
    reason_tags_label: "Reason Tags",
    next_check_label: "Next Check",
    observed_label: "Beobachtet",
    current_label: "aktuell",
    next_plan_label: "naechster Plan",
    data_approx_label: "Daten ca.",
    db_recheck_label: "DB-Recheck",
    map_status_blue: "Blau: kommende Beobachtung geplant.",
    exofop_criteria_label: "ExoFOP-Kriterien erfuellt?",
    yes_label: "Ja",
    no_review_open: "Nein - Review offen",
    admin_exofop_empty: "Keine internen ExoFOP-Prep-Kandidaten.",
    no_candidate_selected: "Kein Kandidat ausgewaehlt.",
    status_add_sector_data: "Erst Sektordaten aus MAST/TESS ergaenzen.",
    status_recheck_possible: "Recheck moeglich, sobald neue TESS-Daten verfuegbar sind.",
    status_waiting_data: "Warten auf neue Daten: aktuell keine passende neue Beobachtung.",
    status_no_recheck: "Kein Recheck geplant: keine zukuenftigen TESS-Sektoren bekannt.",
    next_no_sector: "Kein passender Year-8-Sektor geplant.",
    next_running: "S{sector} laeuft jetzt ({range}).",
    next_in_days: "S{sector} in {days} Tagen ({date}).",
    not_computable_missing_history: "nicht berechenbar - Sektorhistorie fehlt",
    map_status_green: "Gruen: Recheck moeglich - Kandidat liegt im relevanten geplanten Bereich.",
    map_status_yellow: "Gelb: Warten auf neue Daten - aktuell keine neue passende Beobachtung.",
    map_status_red: "Rot: Kein Recheck geplant - keine zukuenftigen TESS-Sektoren bekannt.",
    map_status_missing: "Weiss: Daten fehlen - bitte Sektorhistorie aus MAST/TESS ergaenzen.",
    map_status_hint: "Auswahl zeigt, ob der Kandidat im geplanten TESS-Bereich liegt.",
    match_year8_none: "0 Sektoren",
    match_year8_count: "{count} Sektoren ({list})",
    match_current_running: "S{sector} (laufend)",
    match_current_next: "S{sector} (naechster)",
    observed_unknown_chip: "Sektorhistorie unbekannt",
    planned_unknown_chip: "keine zukuenftigen Sektoren bekannt",
    status_chip_green: "Recheck moeglich",
    status_chip_yellow: "Warten auf neue Daten",
    status_chip_red: "Kein Recheck geplant",
    status_chip_missing: "Daten fehlen",
    tess_label_candidate_sector: "Gruen = Kandidatensektor",
    tess_label_observed: "Blau = beobachtet",
    tess_label_planned: "Gelb = aktuell/geplant",
    tess_label_background: "Grau = Hintergrund",
    chart_legend_map: "Mitte = Sonne/Erde \u00b7 innen = naeher \u00b7 grosse 2D-Kugeln = bessere SNR",
    chart_legend_tess: "Gruen = Kandidatensektor \u00b7 Blau = beobachtet \u00b7 Gelb = aktuell/geplant",
    tess_status_none: "Kein laufender Sektor im Year-8-Ausschnitt.",
    tess_status_running: "S{sector} laeuft aktuell. Restdauer ca. {days} Tage bis {date}.",
    tess_status_next: "Naechster Sektor ist S{sector} und startet in ca. {days} Tagen ({date}).",
    tess_sector_next: "S{sector} (naechster)",
    tess_updated_at: "Quellenstand: {date} (HEASARC + MIT TESS Year 8).",
    color_plus_violet: "{base} + Violett",
    color_green_violet: "Gruen + Violett",
    not_hz: "nicht HZ",
    showing_limited_results: "Zeige 260 von {count} Treffern. Suche nach TIC, um enger zu filtern.",
    no_curve_found: "Keine Lichtkurve gefunden",
    no_curve_selected: "Keine Lichtkurve ausgewaehlt",
    no_curve_for_filter: "Keine passende Lichtkurve im aktuellen Filter.",
    loading_curve: "Lade kombinierte Lichtkurve ...",
    curve_load_failed: "PNG konnte nicht geladen werden. Bitte Pfad/Deploy pruefen.",
    folder_missing: "kein Kandidatenordner",
    selected_path_missing: "kein Level-0-Pfad gefunden",
    status_inactive: "Inaktiv",
    status_active: "Aktiv",
    status_loading: "Startet...",
    status_paused_filter: "Pausiert (Eigenfilter)",
    status_paused_localhost: "Pausiert (localhost)",
    status_error: "Fehler",
    status_unknown_error: "Unbekannter Fehler.",
    analytics_endpoint_missing: "Kein externer Tracking-Endpunkt konfiguriert.",
    analytics_loading: "Tracking-Skript wird geladen.",
    analytics_self_filter_active: "Eigenfilter ist aktiv: eigene Aufrufe werden nicht getrackt.",
    analytics_local_disabled: "Globales Tracking ist lokal deaktiviert (allowLocalhost=false).",
    analytics_tracking_to: "GoatCounter Tracking an {endpoint}",
    admin_login_hint: "Benutzername: Koni",
    admin_self_filter_on: "Aktiv",
    admin_self_filter_off: "Aus",
    admin_self_filter_disable: "Eigene Besuche NICHT zaehlen",
    admin_self_filter_enable: "Eigene Besuche zaehlen",
    admin_goat_title: "GoatCounter",
    admin_goat_text: "Quelle der Wahrheit fuer oeffentliche Besucherzahlen. Die Werte koennen niedriger sein, wenn uBlock, Browser-Schutz oder Consent-Blocking das externe Tracking blockieren.",
    admin_goat_button: "GoatCounter oeffnen",
    admin_local_title: "Lokaler Browser-Fallback",
    admin_local_text: "Zaehlt nur dieses Geraet und diesen Browser via localStorage. Diese Werte sind nicht mit GoatCounter synchronisiert und dienen nur als schnelle lokale Kontrolle.",
    table_country_unknown: "Unknown",
    toast_no_curve_for_candidate: "Fuer diesen Kandidaten ist keine Lichtkurve im Dashboard-Set.",
    toast_filter_hz: "HZ/Violett gefiltert.",
    toast_refresh_data: "Datenbundle: dashboard/build_dashboard_data.py erneut ausfuehren.",
    toast_tree_updated: "Entscheidungsbaum aktualisiert.",
    toast_docs_updated: "Projektlogik aktualisiert.",
    toast_tess_updated: "TESS-Sektorstatus aktualisiert.",
    toast_admin_login_ok: "Admin-Login erfolgreich.",
    toast_admin_login_fail: "Falscher Benutzer oder falsches Passwort.",
    login_failed: "Login fehlgeschlagen.",
    toast_admin_logout: "Admin ausgeloggt.",
    toast_filter_self_on: "Eigenfilter aktiv: eigene Besuche werden nicht gezaehlt.",
    toast_filter_self_off: "Eigenfilter aus: eigene Besuche werden gezaehlt.",
    confirm_reset_stats: "Statistik wirklich zuruecksetzen?",
    toast_stats_reset: "Statistik zurueckgesetzt.",
    toast_admin_refresh: "Admin-Bereich aktualisiert.",
    toast_hints: "Tipps: Links nav nutzen, Karte klicken, TESS-Panel fuer Sektorplanung, Impressum fuer Hinweise, Admin fuer Statistik. UI {version}",
    admin_country_source_unknown: "nicht aufgeloest",
    admin_country_source_unavailable: "nicht verfuegbar",
    year8_description: "Year 8 umfasst S97-S107; S97/98 sind 4-Orbit-Sektoren, danach folgen 9 gedrehte Ueberlappungssektoren.",
    geometry_description: "Sektor-Footprint ca. 24x96 Grad; 4 Kameras in Streifenanordnung, Sektorlaenge typischerweise 27 Tage."
  },
  en: {
    app_title: "CitizenSky \u2013 Exoplanet Candidate Dashboard",
    nav_kandidaten: "Candidates",
    nav_analyse: "Analysis",
    nav_tess: "TESS",
    nav_projekt: "Project",
    about_project_title: "About CitizenSky / Methodology",
    lang_switch_label: "Language",
    nav_tree: "Decision Tree",
    nav_map: "Star Map",
    nav_tess: "TESS",
    nav_curves: "Light Curves",
    nav_table: "Candidates",
    nav_docs: "Project Logic",
    nav_impressum: "Legal",
    nav_admin: "ExoFOP Review",
    sidebar_rule_title: "Reading Rule",
    sidebar_rule_text: "Violet is an extra marker for HZ/top-tier. A candidate can be green and violet at the same time.",
    refresh_data: "Rebuild Data",
    search_placeholder: "Search: TIC, color, HZ, status",
    hint_button_title: "Hints",
    notifications_title: "Dashboard alerts",
    notifications_empty: "No new revaluations in the latest automatic run.",
    notifications_summary: "{total} alerts from the latest automatic run. LIVE_NOW: {live}, UPCOMING: {upcoming}, WAITING_DATA: {waiting}.",
    notifications_updated: "Updated: {date}",
    notification_change_count: "{count} rating fields changed",
    notification_new_sectors: "New sectors: {sectors}",
    notification_recheck_line: "Recheck: {status} \u00b7 current sector: {current} \u00b7 next planned: {next} \u00b7 data approx.: {date}",
    toast_notifications: "{count} dashboard alerts opened.",
    hz_focus: "HZ Focus",
    lede: "Analysis of real TESS data with color classification, light-curve vetting, and an interactive star map.",
    kpi_total: "All Candidates",
    kpi_total_sub: "from manifest",
    kpi_green: "Green",
    kpi_green_sub: "SPC candidates",
    kpi_yellow: "Orange",
    kpi_yellow_sub: "ordinary orange recheck",
    kpi_spc_prep: "SPC Prep",
    kpi_spc_prep_sub: "marked yellow",
    kpi_red: "Red",
    kpi_red_sub: "FP/systematics",
    kpi_violet: "Violet",
    kpi_violet_sub: "HZ/top-tier",
    filter_all: "All",
    filter_green: "Green",
    filter_yellow: "Orange",
    filter_spc_prep: "SPC Prep",
    filter_red: "Red",
    filter_violet: "Violet",
    curves_filter_all: "All",
    curves_filter_green: "Green",
    curves_filter_spc_prep: "Yellow",
    curves_filter_orange: "Orange",
    curves_filter_red: "Red",
    curves_filter_violet: "Violet",
    map_legend_green: "Green = candidate",
    map_legend_yellow: "Orange = under review",
    map_legend_spc_prep: "Yellow = SPC Prep",
    map_legend_red: "Red = FP/rejected",
    map_legend_violet: "Violet ring = HZ focus",
    map_legend_selected: "White ring = selected",
    map_legend_sun: "Sun/Earth reference",
    map_notice_symbolic: "Simplified star-map planning view. Positions, angles, and distances are symbolic and not astronomically to scale.",
    map_notice_gaia_full: "Astrometric sky map based on Gaia (RA/Dec) for all {total} candidates. Angles/layout are astronomical; radial depth is scaled for visualization.",
    map_notice_gaia_mixed: "Mixed map: {gaia} candidates with Gaia RA/Dec ({pct}%), {fallback} still heuristic. Angles are astronomical only for Gaia points.",
    tess_notice_symbolic: "Simplified TESS planning view. Positions, angles, and distances are symbolic and not astronomically to scale.",
    timeline_title: "TESS Coverage Timeline",
    timeline_observed: "Observed so far",
    timeline_planned: "Planned",
    timeline_next: "Next observation",
    timeline_status: "Status",
    selected_title: "Selected Candidate",
    selected_subtitle: "The plain-language rationale is shown here.",
    chip_violet_hz: "Violet / HZ",
    chip_matrix_prefix: "Matrix {value}",
    chip_evidence_prefix: "Evidence {value}",
    chip_curve_available: "Light curve available",
    detail_matrix_status: "Matrix Status",
    detail_matrix_class: "Matrix Class",
    detail_evidence_score: "Evidence Score",
    detail_distance: "Distance",
    detail_period: "Period",
    detail_snr: "SNR",
    detail_transits_visible: "Visible transits",
    detail_matrix_transits: "Matrix transits/sectors",
    detail_radius: "Radius",
    detail_status: "Status",
    detail_shape: "Transit shape",
    detail_sap_pdcsap: "SAP vs PDCSAP",
    detail_oddeven: "Odd/Even",
    detail_secondary: "Secondary eclipse",
    detail_depth: "Depth",
    detail_duration: "Duration",
    detail_depth_stable: "Stable depth?",
    detail_data_gap: "Data-gap risk",
    detail_sector_edge: "Sector-edge risk",
    detail_alias: "Period alias risk",
    detail_rotation: "Activity risk",
    detail_ra: "RA",
    detail_dec: "Dec",
    detail_map_source: "Coordinate source",
    map_source_gaia: "Gaia DR3/DR2 (astrometric)",
    map_source_fallback: "Heuristic (no RA/Dec)",
    matrix_reason_label: "Matrix rationale",
    matrix_next_label: "Next step",
    path_prefix: "Path",
    footer_alert: "\u26a0\ufe0f Preliminary research results. Candidate ratings may change with new TESS data, follow-up observations, or external analyses.",
    footer_about: "About",
    footer_impressum: "Legal",
    footer_privacy: "Privacy",
    footer_github: "GitHub",
    toggle_expand: "Expand section",
    toggle_collapse: "Collapse section",
    tess_compare_expand: "Expand 3D TESS sector map",
    tess_compare_collapse: "Collapse 3D TESS sector map",
    phase_completed: "Completed",
    phase_planned: "Planned",
    phase_running: "Running",
    unknown: "unknown",
    not_available: "not available",
    not_set: "not set",
    no_entries: "No entries yet.",
    table_empty_search: "No candidates for this search.",
    table_count_label: "Candidates",
    table_empty_filter: "No candidates in the current filter.",
    top_candidates_empty: "No publicly released ExoFOP/SPC candidates right now. Internal prep cases are kept in the admin area.",
    followup_candidates_empty: "No follow-up candidates.",
    followup_expand: "Expand follow-up",
    followup_collapse: "Collapse follow-up",
    no_yellow_reason_tags: "No yellow reason tags.",
    no_next_check: "No next check set.",
    yellow_summary_default: "Yellow: scientifically interesting, but not clean enough for automatic green",
    yellow_summary_not_yellow: "This candidate is currently not marked yellow.",
    why_label: "Why?",
    followup_label: "Follow-up",
    reason_tags_label: "Reason tags",
    next_check_label: "Next check",
    observed_label: "Observed",
    current_label: "current",
    next_plan_label: "next plan",
    data_approx_label: "data approx.",
    db_recheck_label: "DB recheck",
    map_status_blue: "Blue: upcoming observation planned.",
    exofop_criteria_label: "ExoFOP criteria met?",
    yes_label: "Yes",
    no_review_open: "No - review open",
    admin_exofop_empty: "No internal ExoFOP prep candidates.",
    no_candidate_selected: "No candidate selected.",
    status_add_sector_data: "Add sector history from MAST/TESS first.",
    status_recheck_possible: "Recheck possible as soon as new TESS data is available.",
    status_waiting_data: "Waiting for new data: no matching new observation yet.",
    status_no_recheck: "No recheck planned: no future TESS sectors known.",
    next_no_sector: "No matching Year-8 sector planned.",
    next_running: "S{sector} is running now ({range}).",
    next_in_days: "S{sector} in {days} days ({date}).",
    not_computable_missing_history: "not computable - sector history missing",
    map_status_green: "Green: recheck possible - candidate lies in the relevant planned area.",
    map_status_yellow: "Yellow: waiting for new data - no suitable new observation right now.",
    map_status_red: "Red: no recheck planned - no future TESS sectors known.",
    map_status_missing: "White: data missing - add sector history from MAST/TESS.",
    map_status_hint: "Selection shows whether the candidate lies in the planned TESS area.",
    match_year8_none: "0 sectors",
    match_year8_count: "{count} sectors ({list})",
    match_current_running: "S{sector} (running)",
    match_current_next: "S{sector} (next)",
    observed_unknown_chip: "sector history unknown",
    planned_unknown_chip: "no future sectors known",
    status_chip_green: "Recheck possible",
    status_chip_yellow: "Waiting for new data",
    status_chip_red: "No recheck planned",
    status_chip_missing: "Data missing",
    tess_label_candidate_sector: "Green = candidate sector",
    tess_label_observed: "Blue = observed",
    tess_label_planned: "Yellow = current/planned",
    tess_label_background: "Gray = background",
    chart_legend_map: "Center = Sun/Earth \u00b7 inner = closer \u00b7 larger 2D markers = better SNR",
    chart_legend_tess: "Green = candidate sector \u00b7 Blue = observed \u00b7 Yellow = current/planned",
    tess_status_none: "No running sector in the Year-8 subset.",
    tess_status_running: "S{sector} is currently running. About {days} days left until {date}.",
    tess_status_next: "Next sector is S{sector} and starts in about {days} days ({date}).",
    tess_sector_next: "S{sector} (next)",
    tess_updated_at: "Data source check: {date} (HEASARC + MIT TESS Year 8).",
    color_plus_violet: "{base} + Violet",
    color_green_violet: "Green + Violet",
    not_hz: "not HZ",
    showing_limited_results: "Showing 260 of {count} matches. Search by TIC to narrow results.",
    no_curve_found: "No light curve found",
    no_curve_selected: "No light curve selected",
    no_curve_for_filter: "No matching light curve for the current filter.",
    loading_curve: "Loading combined light curve ...",
    curve_load_failed: "PNG could not be loaded. Please check path/deploy.",
    folder_missing: "no candidate folder",
    selected_path_missing: "no Level-0 path found",
    status_inactive: "Inactive",
    status_active: "Active",
    status_loading: "Starting...",
    status_paused_filter: "Paused (self filter)",
    status_paused_localhost: "Paused (localhost)",
    status_error: "Error",
    status_unknown_error: "Unknown error.",
    analytics_endpoint_missing: "No external tracking endpoint configured.",
    analytics_loading: "Tracking script is loading.",
    analytics_self_filter_active: "Self filter is active: own visits are not tracked.",
    analytics_local_disabled: "Global tracking is disabled locally (allowLocalhost=false).",
    analytics_tracking_to: "GoatCounter tracking to {endpoint}",
    admin_login_hint: "Username: Koni",
    admin_self_filter_on: "On",
    admin_self_filter_off: "Off",
    admin_self_filter_disable: "Do NOT count own visits",
    admin_self_filter_enable: "Count own visits",
    admin_goat_title: "GoatCounter",
    admin_goat_text: "Source of truth for public visitor analytics. Counts may be lower when uBlock, browser protection, or consent blocking prevents external tracking.",
    admin_goat_button: "Open GoatCounter",
    admin_local_title: "Local browser fallback",
    admin_local_text: "Counts only this device and this browser via localStorage. These values are not synchronized with GoatCounter and are only a quick local check.",
    table_country_unknown: "Unknown",
    toast_no_curve_for_candidate: "No light curve is available for this candidate in the dashboard set.",
    toast_filter_hz: "Filtered to HZ/violet.",
    toast_refresh_data: "Data bundle: re-run dashboard/build_dashboard_data.py.",
    toast_tree_updated: "Decision tree updated.",
    toast_docs_updated: "Project logic updated.",
    toast_tess_updated: "TESS sector status updated.",
    toast_admin_login_ok: "Admin login successful.",
    toast_admin_login_fail: "Wrong username or password.",
    login_failed: "Login failed.",
    toast_admin_logout: "Admin logged out.",
    toast_filter_self_on: "Self filter active: your own visits are not counted.",
    toast_filter_self_off: "Self filter off: your own visits are counted.",
    confirm_reset_stats: "Reset statistics now?",
    toast_stats_reset: "Statistics reset.",
    toast_admin_refresh: "Admin section refreshed.",
    toast_hints: "Tips: use left nav, click map points, use TESS panel for sector planning, Legal panel for notes, Admin for stats. UI {version}",
    admin_country_source_unknown: "not resolved",
    admin_country_source_unavailable: "not available",
    year8_description: "Year 8 includes S97-S107; S97/98 are 4-orbit sectors, followed by 9 rotated overlap sectors.",
    geometry_description: "Sector footprint about 24x96 deg; 4 cameras in strip layout, typical sector duration about 27 days."
  },
  fr: {
    app_title: "CitizenSky \u2013 Exoplanet Candidate Dashboard",
    nav_kandidaten: "Candidats",
    nav_analyse: "Analyse",
    nav_tess: "TESS",
    nav_projekt: "Projet",
    about_project_title: "\u00c0 propos de CitizenSky / M\u00e9thodologie",
    lang_switch_label: "Langue",
    nav_tree: "Arbre de Decision",
    nav_map: "Carte Stellaire",
    nav_tess: "TESS",
    nav_curves: "Courbes de Lumiere",
    nav_table: "Candidats",
    nav_docs: "Logique Projet",
    nav_impressum: "Mentions Legales",
    nav_admin: "ExoFOP Review",
    sidebar_rule_title: "Regle de Lecture",
    sidebar_rule_text: "Le violet est un marqueur supplementaire pour HZ/top-tier. Un candidat peut etre vert et violet en meme temps.",
    refresh_data: "Reconstruire les Donnees",
    search_placeholder: "Recherche: TIC, couleur, HZ, statut",
    hint_button_title: "Astuces",
    notifications_title: "Alertes dashboard",
    notifications_empty: "Aucune nouvelle reevaluation lors du dernier lancement automatique.",
    notifications_summary: "{total} alertes du dernier lancement automatique. LIVE_NOW: {live}, UPCOMING: {upcoming}, WAITING_DATA: {waiting}.",
    notifications_updated: "Mis a jour: {date}",
    notification_change_count: "{count} champs d'evaluation modifies",
    notification_new_sectors: "Nouveaux secteurs: {sectors}",
    notification_recheck_line: "Recheck: {status} \u00b7 secteur actuel: {current} \u00b7 prochain planifie: {next} \u00b7 donnees env.: {date}",
    toast_notifications: "{count} alertes dashboard ouvertes.",
    hz_focus: "Focus HZ",
    lede: "Analyse de vraies donnees TESS avec classification couleur, vetting des courbes de lumiere et carte stellaire interactive.",
    kpi_total: "Tous les Candidats",
    kpi_total_sub: "du manifeste",
    kpi_green: "Vert",
    kpi_green_sub: "candidats SPC",
    kpi_yellow: "Orange",
    kpi_yellow_sub: "orange de reverification",
    kpi_spc_prep: "SPC Prep",
    kpi_spc_prep_sub: "marque jaune",
    kpi_red: "Rouge",
    kpi_red_sub: "FP/systematiques",
    kpi_violet: "Violet",
    kpi_violet_sub: "HZ/top-tier",
    filter_all: "Tous",
    filter_green: "Vert",
    filter_yellow: "Orange",
    filter_spc_prep: "SPC Prep",
    filter_red: "Rouge",
    filter_violet: "Violet",
    curves_filter_all: "Tous",
    curves_filter_green: "Vert",
    curves_filter_spc_prep: "Jaune",
    curves_filter_orange: "Orange",
    curves_filter_red: "Rouge",
    curves_filter_violet: "Violet",
    map_legend_green: "Vert = candidat",
    map_legend_yellow: "Orange = en verification",
    map_legend_spc_prep: "Jaune = SPC Prep",
    map_legend_red: "Rouge = FP/rejete",
    map_legend_violet: "Anneau violet = focus HZ",
    map_legend_selected: "Anneau blanc = selectionne",
    map_legend_sun: "Reference Soleil/Terre",
    map_notice_symbolic: "Vue de planification simplifiee de la carte stellaire. Les positions, angles et distances sont symboliques et non a l'echelle astronomique.",
    map_notice_gaia_full: "Carte du ciel astrometrique basee sur Gaia (RA/Dec) pour les {total} candidats. Les angles/dispositions sont astronomiques; la profondeur radiale est mise a l'echelle pour la visualisation.",
    map_notice_gaia_mixed: "Carte mixte: {gaia} candidats avec RA/Dec Gaia ({pct}%), {fallback} encore heuristiques. Les angles ne sont astronomiques que pour les points Gaia.",
    tess_notice_symbolic: "Vue de planification TESS simplifiee. Les positions, angles et distances sont symboliques et non a l'echelle astronomique.",
    timeline_title: "Chronologie de Couverture TESS",
    timeline_observed: "Deja observe",
    timeline_planned: "Planifie",
    timeline_next: "Prochaine observation",
    timeline_status: "Statut",
    selected_title: "Candidat Selectionne",
    selected_subtitle: "La justification en langage clair apparait ici.",
    chip_violet_hz: "Violet / HZ",
    chip_matrix_prefix: "Matrice {value}",
    chip_evidence_prefix: "Evidence {value}",
    chip_curve_available: "Courbe disponible",
    detail_matrix_status: "Statut matrice",
    detail_matrix_class: "Classe matrice",
    detail_evidence_score: "Score evidence",
    detail_distance: "Distance",
    detail_period: "Periode",
    detail_snr: "SNR",
    detail_transits_visible: "Transits visibles",
    detail_matrix_transits: "Transits/secteurs matrice",
    detail_radius: "Rayon",
    detail_status: "Statut",
    detail_shape: "Forme du transit",
    detail_sap_pdcsap: "SAP vs PDCSAP",
    detail_oddeven: "Odd/Even",
    detail_secondary: "Eclipse secondaire",
    detail_depth: "Profondeur",
    detail_duration: "Duree",
    detail_depth_stable: "Profondeur stable?",
    detail_data_gap: "Risque lacunes",
    detail_sector_edge: "Risque bord secteur",
    detail_alias: "Risque alias periode",
    detail_rotation: "Risque activite",
    detail_ra: "RA",
    detail_dec: "Dec",
    detail_map_source: "Source coordonnees",
    map_source_gaia: "Gaia DR3/DR2 (astrometrique)",
    map_source_fallback: "Heuristique (sans RA/Dec)",
    matrix_reason_label: "Justification matrice",
    matrix_next_label: "Etape suivante",
    path_prefix: "Chemin",
    footer_alert: "\u26a0\ufe0f Resultats de recherche preliminaires. Les evaluations des candidats peuvent changer avec de nouvelles donnees TESS, des suivis ou des analyses externes.",
    footer_about: "A propos",
    footer_impressum: "Mentions Legales",
    footer_privacy: "Confidentialite",
    footer_github: "GitHub",
    toggle_expand: "Ouvrir la section",
    toggle_collapse: "Replier la section",
    tess_compare_expand: "Ouvrir la carte 3D des secteurs TESS",
    tess_compare_collapse: "Replier la carte 3D des secteurs TESS",
    phase_completed: "Termine",
    phase_planned: "Planifie",
    phase_running: "En cours",
    unknown: "inconnu",
    not_available: "indisponible",
    not_set: "non defini",
    no_entries: "Aucune entree pour le moment.",
    table_empty_search: "Aucun candidat pour cette recherche.",
    table_count_label: "Candidats",
    table_empty_filter: "Aucun candidat dans le filtre actuel.",
    top_candidates_empty: "Aucun candidat ExoFOP/SPC publie actuellement. Les cas internes de preparation restent dans la zone admin.",
    followup_candidates_empty: "Aucun candidat de suivi.",
    followup_expand: "Ouvrir le suivi",
    followup_collapse: "Replier le suivi",
    no_yellow_reason_tags: "Aucun tag jaune.",
    no_next_check: "Aucun prochain controle defini.",
    yellow_summary_default: "Jaune: scientifiquement interessant, mais pas assez propre pour le vert automatique",
    yellow_summary_not_yellow: "Ce candidat n'est actuellement pas marque jaune.",
    why_label: "Pourquoi?",
    followup_label: "Suivi",
    reason_tags_label: "Tags de raison",
    next_check_label: "Prochain controle",
    observed_label: "Observe",
    current_label: "actuel",
    next_plan_label: "prochain plan",
    data_approx_label: "donnees env.",
    db_recheck_label: "DB recheck",
    map_status_blue: "Bleu: prochaine observation planifiee.",
    exofop_criteria_label: "Criteres ExoFOP remplis?",
    yes_label: "Oui",
    no_review_open: "Non - revue ouverte",
    admin_exofop_empty: "Aucun candidat interne ExoFOP prep.",
    no_candidate_selected: "Aucun candidat selectionne.",
    status_add_sector_data: "Ajouter d'abord l'historique des secteurs depuis MAST/TESS.",
    status_recheck_possible: "Reverification possible des que de nouvelles donnees TESS sont disponibles.",
    status_waiting_data: "En attente de nouvelles donnees: aucune nouvelle observation correspondante pour l'instant.",
    status_no_recheck: "Aucune reverification planifiee: aucun futur secteur TESS connu.",
    next_no_sector: "Aucun secteur Year-8 correspondant planifie.",
    next_running: "S{sector} est en cours ({range}).",
    next_in_days: "S{sector} dans {days} jours ({date}).",
    not_computable_missing_history: "non calculable - historique de secteurs manquant",
    map_status_green: "Vert: reverification possible - le candidat se trouve dans la zone planifiee pertinente.",
    map_status_yellow: "Jaune: attente de nouvelles donnees - aucune nouvelle observation adaptee actuellement.",
    map_status_red: "Rouge: aucune reverification planifiee - aucun futur secteur TESS connu.",
    map_status_missing: "Blanc: donnees manquantes - ajouter l'historique des secteurs depuis MAST/TESS.",
    map_status_hint: "La selection montre si le candidat se situe dans la zone TESS planifiee.",
    match_year8_none: "0 secteur",
    match_year8_count: "{count} secteurs ({list})",
    match_current_running: "S{sector} (en cours)",
    match_current_next: "S{sector} (prochain)",
    observed_unknown_chip: "historique de secteurs inconnu",
    planned_unknown_chip: "aucun futur secteur connu",
    status_chip_green: "Reverification possible",
    status_chip_yellow: "Attente de nouvelles donnees",
    status_chip_red: "Aucune reverification planifiee",
    status_chip_missing: "Donnees manquantes",
    tess_label_candidate_sector: "Vert = secteur candidat",
    tess_label_observed: "Bleu = observe",
    tess_label_planned: "Jaune = actuel/planifie",
    tess_label_background: "Gris = arriere-plan",
    chart_legend_map: "Centre = Soleil/Terre \u00b7 interieur = plus proche \u00b7 grands points 2D = meilleur SNR",
    chart_legend_tess: "Vert = secteur candidat \u00b7 Bleu = observe \u00b7 Jaune = actuel/planifie",
    tess_status_none: "Aucun secteur en cours dans l'extrait Year-8.",
    tess_status_running: "S{sector} est en cours. Environ {days} jours restants jusqu'au {date}.",
    tess_status_next: "Le prochain secteur est S{sector} et commence dans environ {days} jours ({date}).",
    tess_sector_next: "S{sector} (prochain)",
    tess_updated_at: "Date des sources: {date} (HEASARC + MIT TESS Year 8).",
    color_plus_violet: "{base} + Violet",
    color_green_violet: "Vert + Violet",
    not_hz: "pas HZ",
    showing_limited_results: "Affichage de 260 resultats sur {count}. Recherchez par TIC pour filtrer davantage.",
    no_curve_found: "Aucune courbe de lumiere trouvee",
    no_curve_selected: "Aucune courbe de lumiere selectionnee",
    no_curve_for_filter: "Aucune courbe correspondant au filtre actuel.",
    loading_curve: "Chargement de la courbe de lumiere combinee ...",
    curve_load_failed: "Le PNG n'a pas pu etre charge. Verifiez le chemin/deploiement.",
    folder_missing: "aucun dossier candidat",
    selected_path_missing: "aucun chemin Level-0 trouve",
    status_inactive: "Inactif",
    status_active: "Actif",
    status_loading: "Demarrage...",
    status_paused_filter: "Pause (filtre propre)",
    status_paused_localhost: "Pause (localhost)",
    status_error: "Erreur",
    status_unknown_error: "Erreur inconnue.",
    analytics_endpoint_missing: "Aucun endpoint de suivi externe configure.",
    analytics_loading: "Le script de suivi est en cours de chargement.",
    analytics_self_filter_active: "Le filtre propre est actif: vos propres visites ne sont pas tracees.",
    analytics_local_disabled: "Le suivi global est desactive en local (allowLocalhost=false).",
    analytics_tracking_to: "Suivi GoatCounter vers {endpoint}",
    admin_login_hint: "Nom d'utilisateur: Koni",
    admin_self_filter_on: "Actif",
    admin_self_filter_off: "Off",
    admin_self_filter_disable: "NE PAS compter mes visites",
    admin_self_filter_enable: "Compter mes visites",
    admin_goat_title: "GoatCounter",
    admin_goat_text: "Source de reference pour les statistiques publiques. Les valeurs peuvent etre plus basses si uBlock, la protection du navigateur ou le blocage du consentement empeche le tracking externe.",
    admin_goat_button: "Ouvrir GoatCounter",
    admin_local_title: "Fallback navigateur local",
    admin_local_text: "Compte seulement cet appareil et ce navigateur via localStorage. Ces valeurs ne sont pas synchronisees avec GoatCounter et servent uniquement de controle local rapide.",
    table_country_unknown: "Unknown",
    toast_no_curve_for_candidate: "Aucune courbe disponible pour ce candidat dans le set dashboard.",
    toast_filter_hz: "Filtre HZ/violet actif.",
    toast_refresh_data: "Bundle de donnees: relancer dashboard/build_dashboard_data.py.",
    toast_tree_updated: "Arbre de decision mis a jour.",
    toast_docs_updated: "Logique projet mise a jour.",
    toast_tess_updated: "Statut des secteurs TESS mis a jour.",
    toast_admin_login_ok: "Connexion admin reussie.",
    toast_admin_login_fail: "Nom d'utilisateur ou mot de passe incorrect.",
    login_failed: "Echec de connexion.",
    toast_admin_logout: "Admin deconnecte.",
    toast_filter_self_on: "Filtre propre actif: vos visites ne sont pas comptees.",
    toast_filter_self_off: "Filtre propre desactive: vos visites sont comptees.",
    confirm_reset_stats: "Reinitialiser les statistiques maintenant?",
    toast_stats_reset: "Statistiques reinitialisees.",
    toast_admin_refresh: "Section admin actualisee.",
    toast_hints: "Astuces: utilisez la navigation a gauche, cliquez la carte, utilisez le panneau TESS pour la planification, Mentions Legales pour les notes, Admin pour les stats. UI {version}",
    admin_country_source_unknown: "non resolu",
    admin_country_source_unavailable: "indisponible",
    year8_description: "L'annee 8 couvre S97-S107; S97/98 sont des secteurs a 4 orbites, suivis de 9 secteurs de recouvrement tournes.",
    geometry_description: "Empreinte secteur env. 24x96 deg; 4 cameras en bande, duree typique d'un secteur env. 27 jours."
  }
};

export const projectFlowSteps = [
  "1) Level 0: Gaia/TIC-Grunddaten + Farbbaum",
  "2) Level 1: TESS-Lichtkurven + Rohkandidaten",
  "3) Level 2: planetare Plausibilitaet",
  "4) Level 3: externe Katalogpruefung",
  "5) Level 4: Timing, TTV und Alias-Kontrolle",
  "6) Level 5: Detailvalidierung und FP-Tests",
  "7) Level 6: Kandidaten-Dossier und Follow-up",
  "8) Dashboard + Candidate Matrix + Monitoring"
];

export const projectLevels = [
  {
    name: "Level 0 - Farbb\u00e4ume und Distanzfilter",
    text: "Aus Gaia- und TIC-Grunddaten entsteht die erste kontrollierte Zielmenge: nahe Sterne werden nach Entfernung, Sternklasse und Datenqualitaet vorsortiert, bevor Transit-Signale ueberhaupt bewertet werden.",
    details: [
      "Gaia/TIC-Grunddaten sammeln und Distanzklassen nach Lichtjahren bilden.",
      "Sternfilter nach Temperatur, Radius, Helligkeit und RUWE anwenden.",
      "K-, G- und M-Sterne getrennt strukturieren.",
      "Ordnerstruktur und Farblogik fuer gruen, gelb, rot und HZ/violett erzeugen."
    ]
  },
  {
    name: "Level 1 - Rohkandidaten",
    text: "TESS-Lichtkurven werden nicht nur nach einzelnen Dips durchsucht, sondern mit systematischen Transit-Suchlaeufen und ersten Qualitaetsplots in messbare Rohkandidaten uebersetzt.",
    details: [
      "TESS-Lichtkurven laden und SAP sowie PDCSAP gegenueberstellen.",
      "BLS/TLS-Transit-Suche auf periodische Signale anwenden.",
      "Periode, Tiefe, Dauer und SNR berechnen.",
      "Erste Foldplots und Referenzplots fuer Sichtpruefung erzeugen."
    ]
  },
  {
    name: "Level 2 - Planetare Plausibilitaet",
    text: "Die Rohsignale werden gegen einfache planetare Erwartungswerte und Transitgeometrie geprueft. Ziel ist eine fruehe Trennung zwischen plausiblen Transits, Artefakten und unzureichender Datenlage.",
    details: [
      "Transitform pruefen, insbesondere U-Shape vs. V-Shape.",
      "Mindestanzahl sichtbarer Transits verlangen.",
      "Radiusabschaetzung aus Tiefe und Sternradius ableiten.",
      "Habitable-Zone-Check berechnen und SPC / SPC_ART / Unsicher vergeben."
    ]
  },
  {
    name: "Level 3 - Externe Pruefung",
    text: "Kandidaten werden gegen externe astronomische Kataloge und Nachbarquellen geprueft. So werden bekannte Objekte, Eclipsing Binaries und moegliche Kontaminationen sichtbar.",
    details: [
      "ExoFOP-, TOI- und SIMBAD-Abgleich durchfuehren.",
      "Bekannte Planeten oder Eclipsing Binaries erkennen.",
      "Gaia-Nachbarsterne und moegliche Blend-Quellen pruefen.",
      "Unbekannte Kandidaten von bereits katalogisierten Faellen trennen."
    ]
  },
  {
    name: "Level 4 - TTV / Timing",
    text: "Das Timing prueft, ob ein Signal periodisch stabil ist oder durch Datenfenster, Alias-Loesungen oder Transit-Timing-Variationen erklaert werden koennte.",
    details: [
      "O-C Analyse und Transit-Timing-Variationen pruefen.",
      "Segmentanalyse fuer einzelne Sektoren und Zeitfenster anwenden.",
      "Periodenstabilitaet und Alias-Risiken bewerten.",
      "Datenfensterqualitaet, Randlagen und Luecken dokumentieren."
    ]
  },
  {
    name: "Level 5 - Detailvalidierung",
    text: "In der Detailvalidierung werden klassische False-Positive-Szenarien aktiv gesucht. Ein Kandidat soll mehrere unabhaengige Plausibilitaetstests ueberstehen.",
    details: [
      "Odd/Even-Test und Secondary-Eclipse-Suche durchfuehren.",
      "SAP vs. PDCSAP vergleichen und Aperture-/Nachbarstern-Checks nutzen.",
      "Rotationsanalyse und Aktivitaetspruefung einbeziehen.",
      "BY-Dra-Risiko und andere stellare Variabilitaet markieren."
    ]
  },
  {
    name: "Level 6 - Kandidaten-Dossier",
    text: "Am Ende wird kein endgueltiger Planet behauptet, sondern ein nachvollziehbares Kandidaten-Dossier erzeugt: Status, Evidenz, Unsicherheiten und naechste Beobachtungsschritte.",
    details: [
      "Evidence Score, SPC-Status, HZ-Klasse und Recheck-Status zusammenfassen.",
      "RV Needed / Follow-up Ready und naechste TESS-Beobachtung ausweisen.",
      "Export fuer spaetere Nachpruefung und erneutes Vetting erzeugen.",
      "Entscheidung offen halten, wenn Datenlage oder externe Evidenz unvollstaendig ist."
    ]
  },
  {
    name: "Dashboard + Candidate Matrix",
    text: "Dashboard und Matrix machen den Zwischenstand sichtbar, nicht die finale Wahrheit. Sie zeigen, warum ein Kandidat weiter verfolgt, beobachtet, zurueckgestellt oder depriorisiert wird.",
    details: [
      "Kandidatenstatus, Evidence Score, Transitanzahl, SNR, Radius und HZ-Status anzeigen.",
      "Recheck-Ampel, naechste Aktion und Datenfenster-Risiken sichtbar machen.",
      "Vorlaeufigkeit klar markieren: Ergebnisse sind nicht vollstaendig und koennen sich mit neuen Daten aendern.",
      "Pipeline-Entscheidungen transparent machen, statt nur Lichtkurven-Dips zu sammeln."
    ]
  }
];

export const projectScripts = [
  { script: "dashboard/build_dashboard_data.py", does: "Baut das Datenbundle fuer die Live-UI (Kandidaten, Matrix-Felder, Kurvenpfade, Kennzahlen).", why: "Zentrale Quelle fuer Dashboard-Transparenz und konsistente Filter.", level: "Dashboard / alle Level" },
  { script: "build_dashboard_data.py", does: "Aelterer Builder im Repo-Root fuer statische Dashboard-Daten.", why: "Rueckwaertskompatibel fuer fruehere Ablaufe.", level: "Dashboard (legacy)" },
  { script: "main/masterscript_v2.py", does: "Orchestriert groessere Pipeline-Laeufe ueber mehrere Verarbeitungsschritte.", why: "Weniger manuelle Einzelstarts, reproduzierbare Runs.", level: "Pipeline-Steuerung" },
  { script: "main/build_level0_level_tree.py", does: "Erzeugt die Level-0 Baumstruktur und Auswertungsgrundlage.", why: "Saubere Navigations- und Entscheidungsstruktur fuer alle spaeteren Schritte.", level: "Level 0" },
  { script: "main/apply_ly_folder_color_tags.py", does: "Setzt Farb-/Status-Tags in Distanzordnern.", why: "Schneller visueller Zugriff auf Prioritaet und Risiko.", level: "Level 0" },
  { script: "main/organize_review_by_distance.py", does: "Ordnet Kandidaten review-freundlich nach Distanzbloecken.", why: "Ergonomische Sichtung statt ungeordneter Massenliste.", level: "Level 0/1" },
  { script: "main/create_distance_range_archive.py", does: "Bildet Archivstrukturen pro Distanzbereich.", why: "Nachvollziehbarkeit historischer Stufen und Snapshots.", level: "Level 0 Archiv" },
  { script: "main/remove_red_level0_folders.py", does: "Bereinigt/depriorisiert rot markierte Level-0 Ordner.", why: "Fokus auf hochwertige Kandidaten, weniger Rauschen.", level: "Level 0 Hygiene" },
  { script: "main/level2_planet_check.py", does: "Fuehrt den planetaren Plausibilitaetscheck fuer Level 2 aus.", why: "Schnelle Trennung planetenartig vs. problematisch.", level: "Level 2" },
  { script: "main/assess_spc_candidate.py", does: "Bewertet SPC-Reife pro Kandidat.", why: "Objektiviert Gruen/SPC-Entscheidungen.", level: "Level 2/3" },
  { script: "main/build_candidate_matrix.py", does: "Baut die Kandidaten-Matrix mit Status, Scores und naechsten Schritten.", why: "Nachvollziehbare, automatisierte Entscheidungsschicht.", level: "Matrix / alle Level" },
  { script: "main/evidence_vetting.py", does: "Sammelt Vetting-Evidenz (Signalqualitaet, Konsistenz, Risiken).", why: "Fundierte Entscheidungen statt Bauchgefuehl.", level: "Level 3-5" },
  { script: "main/external_catalog_crossmatch.py", does: "Crossmatch gegen externe Kataloge/TOI-Informationen.", why: "Bekannte Funde, FP und neue Kandidaten sauber trennen.", level: "Level 3" },
  { script: "main/build_green_purple_hz_review.py", does: "Baut Review-Set fuer Gruen/Violett/HZ Kandidaten.", why: "Fokus auf wissenschaftlich interessante Targets.", level: "Level 3/4" },
  { script: "main/make_new_candidate_shortlist.py", does: "Erstellt priorisierte Shortlist neuer Kandidaten.", why: "Zeit in die besten Folgeziele investieren.", level: "Level 3" },
  { script: "main/level4_candidate_filter.py", does: "Filtert Kandidaten fuer tieferen Level-4 Check.", why: "Entlastet TTV-Analyse von unpassenden Faellen.", level: "Level 4" },
  { script: "main/ttv_analyse.py", does: "Berechnet Transit Timing Variation Metriken.", why: "Dynamische Systeme und Alias-Probleme erkennen.", level: "Level 4" },
  { script: "main/ttv_make_graphics.py", does: "Erstellt O-C/TTV Grafiken fuer die Sichtung.", why: "Komplexe Timingmuster visuell plausibel pruefen.", level: "Level 4" },
  { script: "main/vet_green_candidate_plots.py", does: "Vetting der gruenen Kandidatenplots.", why: "Gruene Kandidaten vor finalem SPC-Label absichern.", level: "Level 4/5" },
  { script: "main/run_level5_green_purple_batch.py", does: "Batch-Detailvalidierung fuer gruene/violette Gruppen.", why: "Skaliert Tieftests ueber viele Kandidaten.", level: "Level 5" },
  { script: "main/advanced_bayesian_vetting.py", does: "Bayesianisches Vetting fuer Kandidatenwahrscheinlichkeiten.", why: "Robustere Priorisierung bei unsicheren Faellen.", level: "Level 5+" },
  { script: "main/check_new_tess_sectors.py", does: "Prueft neue TESS-Sektoren fuer bestehende Kandidaten.", why: "NEEDS_MORE_DATA Faelle automatisch reaktivieren.", level: "Monitoring" },
  { script: "main/monitor_insufficient_data.py", does: "Ueberwacht Kandidaten mit unzureichender Datenlage.", why: "Kein relevanter Kandidat geht im Wartestatus verloren.", level: "Monitoring" },
  { script: "main/fill_level0_combined_pngs.py", does: "Ergaenzt fehlende kombinierte Lichtkurven-PNGs in Level 0.", why: "Vollstaendige visuelle Basis fuer Dashboard und Vetting.", level: "Assets / Level 0" },
  { script: "main/link_level0_lightcurve_pngs.py", does: "Verknuepft bzw. synchronisiert Lichtkurvenpfade.", why: "Verhindert fehlende Kurven durch Pfaddrift.", level: "Assets / Dashboard" },
  { script: "main/export_all_reference_combined_plots.py", does: "Exportiert Referenzplots fuer Sammelreviews.", why: "Vergleichbarer Plotstandard ueber alle Kandidaten.", level: "Reporting" },
  { script: "special/compute_hz.py", does: "Berechnet HZ-Klassen (konservativ/optimistisch).", why: "Violett/HZ-Markierung wissenschaftlich begruenden.", level: "HZ Spezial" },
  { script: "special/spc_art_vetter.py", does: "Spezialvetting fuer SPC_ART und Artefaktfaelle.", why: "Grenzfaelle systematisch statt ad hoc bewerten.", level: "Spezial / Vetting" },
  { script: "special/tic13096842_analysis.py", does: "Einzelfall-Deepdive fuer TIC 13096842.", why: "Dokumentiert schwierige Referenzfaelle fuer Methodik.", level: "Case Study" },
  { script: "special/tic13096842_sector98.py", does: "Sektor-spezifischer Deepdive zu TIC 13096842.", why: "Zeigt, wie sektorale Inkonsistenz untersucht wird.", level: "Case Study" }
];

export const projectFlowStepsI18n = {
  de: projectFlowSteps,
  en: [
    "1) Level 0: Gaia/TIC base data + color tree",
    "2) Level 1: TESS light curves + raw candidates",
    "3) Level 2: planetary plausibility",
    "4) Level 3: external catalog checks",
    "5) Level 4: timing, TTV and alias control",
    "6) Level 5: detailed validation and FP tests",
    "7) Level 6: candidate dossier and follow-up",
    "8) Dashboard + Candidate Matrix + monitoring"
  ],
  fr: [
    "1) Niveau 0: donnees Gaia/TIC + arbre couleur",
    "2) Niveau 1: courbes TESS + candidats bruts",
    "3) Niveau 2: plausibilite planetaire",
    "4) Niveau 3: verification de catalogues externes",
    "5) Niveau 4: timing, TTV et controle d'alias",
    "6) Niveau 5: validation detaillee et tests FP",
    "7) Niveau 6: dossier candidat et suivi",
    "8) Dashboard + matrice candidats + monitoring"
  ]
};

export const projectLevelsI18n = {
  de: projectLevels,
  en: [
    { name: "Level 0 - Color Trees and Distance Filters", text: "Gaia and TIC base data define the first controlled target set before any transit signal is interpreted.", details: ["Collect Gaia/TIC base data and group distances in light-years.", "Filter stars by temperature, radius, brightness, and RUWE.", "Structure K, G, and M stars separately.", "Create the folder tree and color logic for green, yellow, red, and HZ/purple."] },
    { name: "Level 1 - Raw Candidates", text: "TESS light curves are converted into measurable raw candidates with systematic transit searches and first quality plots.", details: ["Load TESS light curves and compare SAP with PDCSAP.", "Run BLS/TLS transit searches.", "Calculate period, depth, duration, and SNR.", "Generate first folded plots and reference plots."] },
    { name: "Level 2 - Planetary Plausibility", text: "Raw signals are checked against basic planetary expectations and transit geometry before they move deeper into the pipeline.", details: ["Check transit shape, especially U-shape versus V-shape.", "Require a minimum number of visible transits.", "Estimate radius from depth and stellar radius.", "Run the habitable-zone check and assign SPC / SPC_ART / uncertain."] },
    { name: "Level 3 - External Check", text: "Candidates are crossmatched against external catalogs and neighboring sources to identify known objects and contamination risks.", details: ["Crossmatch ExoFOP, TOI, and SIMBAD.", "Recognize known planets or eclipsing binaries.", "Inspect Gaia neighboring stars and possible blend sources.", "Separate unknown candidates from cataloged cases."] },
    { name: "Level 4 - Timing / TTV", text: "Timing tests evaluate whether a signal is stable, affected by data windows, or consistent with alias solutions or TTVs.", details: ["Run O-C analysis and check transit-timing variations.", "Analyze segments by sector and time window.", "Assess period stability and alias risks.", "Document data-window quality, sector edges, and gaps."] },
    { name: "Level 5 - Detailed Validation", text: "Classic false-positive scenarios are actively searched for; strong candidates should survive several independent checks.", details: ["Run odd/even tests and secondary-eclipse searches.", "Compare SAP with PDCSAP and inspect aperture/neighboring-star risks.", "Include rotation and stellar-activity analysis.", "Flag BY Dra risk and related stellar variability."] },
    { name: "Level 6 - Candidate Dossier", text: "The final product is a traceable candidate dossier, not a planet confirmation: status, evidence, uncertainty, and follow-up route.", details: ["Summarize evidence score, SPC status, HZ class, and recheck status.", "Show RV Needed / Follow-up Ready and the next TESS observation.", "Export records for later rechecking and renewed vetting.", "Keep decisions provisional when evidence remains incomplete."] },
    { name: "Dashboard + Candidate Matrix", text: "The dashboard exposes the provisional state and explains why a candidate is followed, rechecked, paused, or deprioritized.", details: ["Show candidate status, evidence score, transit count, SNR, radius, and HZ status.", "Expose recheck signal, next action, and data-window risks.", "Mark results as provisional and incomplete.", "Make pipeline decisions transparent instead of listing light-curve dips."] }
  ],
  fr: [
    { name: "Niveau 0 - Arbres couleur et filtres de distance", text: "Les donnees Gaia et TIC definissent un premier ensemble cible controle avant toute interpretation de transit.", details: ["Collecter les donnees Gaia/TIC et classer les distances en annees-lumiere.", "Filtrer par temperature, rayon, luminosite et RUWE.", "Structurer separement les etoiles K, G et M.", "Creer l'arborescence et la logique couleur vert, jaune, rouge et HZ/violet."] },
    { name: "Niveau 1 - Candidats bruts", text: "Les courbes TESS sont transformees en candidats mesurables par recherches de transit et premiers graphiques de qualite.", details: ["Charger les courbes TESS et comparer SAP avec PDCSAP.", "Lancer les recherches BLS/TLS.", "Calculer periode, profondeur, duree et SNR.", "Produire les premiers graphiques plies et de reference."] },
    { name: "Niveau 2 - Plausibilite planetaire", text: "Les signaux bruts sont confrontes aux attentes planetaires simples et a la geometrie de transit.", details: ["Verifier la forme du transit, surtout U-shape vs V-shape.", "Exiger un nombre minimal de transits visibles.", "Estimer le rayon avec profondeur et rayon stellaire.", "Verifier la zone habitable et assigner SPC / SPC_ART / incertain."] },
    { name: "Niveau 3 - Verification externe", text: "Les candidats sont croises avec des catalogues externes et les sources voisines pour identifier objets connus et contaminations.", details: ["Croiser ExoFOP, TOI et SIMBAD.", "Reconnaitre planetes connues ou binaires a eclipses.", "Verifier les etoiles voisines Gaia et les sources de blend.", "Separer les candidats inconnus des cas catalogues."] },
    { name: "Niveau 4 - Timing / TTV", text: "Le timing verifie la stabilite du signal et les risques lies aux fenetres de donnees, alias ou TTV.", details: ["Faire l'analyse O-C et verifier les TTV.", "Analyser les segments par secteur et fenetre temporelle.", "Evaluer stabilite de periode et risques d'alias.", "Documenter qualite des fenetres, bords de secteur et lacunes."] },
    { name: "Niveau 5 - Validation detaillee", text: "Les scenarios classiques de faux positifs sont recherches activement par plusieurs controles independants.", details: ["Faire les tests odd/even et la recherche d'eclipse secondaire.", "Comparer SAP et PDCSAP et verifier aperture/voisins.", "Inclure rotation et activite stellaire.", "Marquer le risque BY Dra et la variabilite stellaire."] },
    { name: "Niveau 6 - Dossier candidat", text: "Le resultat est un dossier tracable, pas une confirmation: statut, evidence, incertitudes et suite de suivi.", details: ["Resumer evidence score, statut SPC, classe HZ et statut recheck.", "Indiquer RV Needed / Follow-up Ready et la prochaine observation TESS.", "Exporter pour verification ulterieure et nouveau vetting.", "Garder les decisions provisoires si l'evidence est incomplete."] },
    { name: "Dashboard + Matrice Candidats", text: "Le dashboard montre l'etat provisoire et explique pourquoi un candidat avance, attend, est recontrole ou depriorise.", details: ["Afficher statut, evidence score, nombre de transits, SNR, rayon et HZ.", "Montrer l'alerte recheck, la prochaine action et les risques de fenetre.", "Signaler que les resultats sont provisoires et incomplets.", "Rendre les decisions du pipeline transparentes, pas seulement lister des dips."] }
  ]
};

export const labelLegend = [
  ["SPC", "Strong Planet Candidate"],
  ["SPC_ART", "Strong Planet Candidate with artifact/systematics concern"],
  ["SPC_FOLLOWUP_READY", "Yellow SPC-prep candidate, separated from ordinary yellow"],
  ["HZ_RECHECK", "Candidate in/near HZ, needs recheck"],
  ["SPC_RV_NEEDED", "Strong candidate, radial velocity follow-up needed"],
  ["EB_RISK", "Possible eclipsing binary risk"],
  ["FP_BYDRA", "Likely false positive due to BY Dra / stellar activity"],
  ["REJECTED", "Rejected candidate"],
  ["NEEDS_MORE_TESS_DATA", "Not enough TESS coverage yet"]
];

export const labelLegendLocalized = {
  de: {
    SPC: "Starker Planetenkandidat",
    SPC_ART: "Starker Planetenkandidat mit Artefakt- oder Systematikverdacht",
    SPC_FOLLOWUP_READY: "Gelber SPC-Prep-Kandidat, getrennt von normalem Gelb",
    HZ_RECHECK: "Kandidat in/nahe der HZ, Nachpruefung noetig",
    SPC_RV_NEEDED: "Starker Kandidat, Radialgeschwindigkeits-Follow-up noetig",
    EB_RISK: "Moegliches Risiko einer bedeckungsveraenderlichen Doppelsternquelle",
    FP_BYDRA: "Wahrscheinlicher False Positive durch BY-Dra-/Sternaktivitaet",
    REJECTED: "Abgelehnter Kandidat",
    NEEDS_MORE_TESS_DATA: "Noch nicht genug TESS-Abdeckung"
  },
  en: Object.fromEntries(labelLegend),
  fr: {
    SPC: "Candidat planetaire fort",
    SPC_ART: "Candidat fort avec suspicion d'artefact ou de systematique",
    SPC_FOLLOWUP_READY: "Candidat SPC-prep jaune, separe du jaune ordinaire",
    HZ_RECHECK: "Candidat dans/pres de la HZ, reverification necessaire",
    SPC_RV_NEEDED: "Candidat fort, suivi en vitesse radiale necessaire",
    EB_RISK: "Risque possible de binaire a eclipses",
    FP_BYDRA: "Faux positif probable du a BY Dra / activite stellaire",
    REJECTED: "Candidat rejete",
    NEEDS_MORE_TESS_DATA: "Couverture TESS encore insuffisante"
  }
};

export function normalizeLanguage(lang) {
  const safe = String(lang || "").trim().toLowerCase();
  if (SUPPORTED_LANGS.includes(safe)) return safe;
  if (safe.startsWith("de")) return "de";
  if (safe.startsWith("en")) return "en";
  if (safe.startsWith("fr")) return "fr";
  return "de";
}

export function detectInitialLanguage() {
  try {
    const persisted = localStorage.getItem(LANGUAGE_KEY);
    if (persisted) return normalizeLanguage(persisted);
  } catch (_) {}
  return normalizeLanguage((navigator.languages && navigator.languages[0]) || navigator.language || "de");
}

export function currentLocale() {
  return LANGUAGE_LOCALES[state.lang] || LANGUAGE_LOCALES.de;
}

export function t(key, vars = {}) {
  const table = I18N[state.lang] || I18N.de;
  const fallback = I18N.de || {};
  const template = table[key] !== undefined ? table[key] : fallback[key];
  if (template === undefined) return key;
  return String(template).replace(/\{(\w+)\}/g, (_, token) => {
    const value = vars[token];
    return value === undefined || value === null ? "" : String(value);
  });
}

export function setLanguage(lang, persist = true) {
  state.lang = normalizeLanguage(lang);
  if (persist) {
    try {
      localStorage.setItem(LANGUAGE_KEY, state.lang);
    } catch (_) {}
  }
}

state.lang = detectInitialLanguage();

export function formatNumber(value) {
  return new Intl.NumberFormat(currentLocale()).format(value || 0);
}

export function formatMaybe(value, fallback = "-") {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text ? text : fallback;
}

export function formatFloat(value, digits = 2, fallback = "-") {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return number.toLocaleString(currentLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

export function parseIsoDate(value, endOfDay = false) {
  if (!value) return null;
  const stamp = endOfDay ? "23:59:59Z" : "00:00:00Z";
  return new Date(value + "T" + stamp);
}

export function formatDate(value) {
  const date = parseIsoDate(value);
  if (!date || Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(currentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(date);
}

export function formatDateRange(start, end) {
  return formatDate(start) + " - " + formatDate(end);
}

export function daysDiff(fromDate, toDate) {
  const diff = toDate.getTime() - fromDate.getTime();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

export function normalizeSectorList(values) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const normalized = [];
  values.forEach((value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return;
    const sector = Math.round(number);
    if (sector < 1 || sector > tessMission.totalNumberedSectorsPlanned) return;
    if (seen.has(sector)) return;
    seen.add(sector);
    normalized.push(sector);
  });
  normalized.sort((a, b) => a - b);
  return normalized;
}

export function buildTessScheduleState() {
  const now = new Date();
  const schedule = tessMission.year8Sectors.map((item) => {
    const startDate = parseIsoDate(item.start);
    const endDate = parseIsoDate(item.end, true);
    let phase = "completed";
    if (now < startDate) phase = "planned";
    else if (now <= endDate) phase = "running";
    return { ...item, startDate, endDate, phase };
  });
  const current = schedule.find((item) => item.phase === "running") || null;
  const upcoming = schedule.filter((item) => item.phase === "planned");
  const completed = schedule.filter((item) => item.phase === "completed");
  return { now, schedule, current, upcoming, completed, next: upcoming[0] || null };
}

export function formatSectorList(sectors, maxItems = 9) {
  const list = normalizeSectorList(sectors);
  if (!list.length) return "-";
  const shown = list.slice(0, maxItems).map((sector) => "S" + sector);
  const suffix = list.length > maxItems ? " +" + (list.length - maxItems) : "";
  return shown.join(", ") + suffix;
}

export function sectorPhase(sector) {
  const safe = Math.max(1, Math.round(Number(sector) || 1));
  return ((safe - 1) % 13) + 1;
}

export function formatMonthYear(value) {
  const date = parseIsoDate(value);
  if (!date || Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(currentLocale(), {
    month: "short",
    year: "numeric"
  }).format(date);
}

export function formatDuration(seconds) {
  const safe = Math.max(0, Math.round(Number(seconds) || 0));
  if (safe < 60) return safe + "s";
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  if (mins < 60) return mins + "m " + secs + "s";
  const hours = Math.floor(mins / 60);
  const restMins = mins % 60;
  return hours + "h " + restMins + "m";
}

export function formatDateTime(isoValue) {
  if (!isoValue) return "-";
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(currentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function formatNotificationValue(value, fallback = "-") {
  if (value === undefined || value === null || value === "") return fallback;
  return value;
}

export function localizeScriptLevel(text) {
  const source = String(text || "");
  if (state.lang === "de") return source;
  if (state.lang === "en") {
    return source
      .replace(/alle Level/g, "all levels")
      .replace(/Level/g, "Level")
      .replace(/Archiv/g, "Archive")
      .replace(/Hygiene/g, "Hygiene")
      .replace(/Spezial/g, "Special")
      .replace(/Reporting/g, "Reporting")
      .replace(/Monitoring/g, "Monitoring");
  }
  return source
    .replace(/alle Level/g, "tous niveaux")
    .replace(/Level/g, "Niveau")
    .replace(/Archiv/g, "Archive")
    .replace(/Hygiene/g, "Hygiene")
    .replace(/Spezial/g, "Special")
    .replace(/Reporting/g, "Reporting")
    .replace(/Monitoring/g, "Monitoring");
}

export function localizeScriptText(text) {
  const source = String(text || "");
  if (state.lang === "de") return source;
  if (state.lang === "en") {
    return source
      .replace(/Farbbaum/g, "color tree")
      .replace(/Baumstruktur/g, "tree structure")
      .replace(/Entscheidungsbaum/g, "decision tree")
      .replace(/Lichtkurven/g, "light curves")
      .replace(/Rohkandidaten/g, "raw candidates")
      .replace(/Kandidaten/g, "candidates")
      .replace(/Kandidat/g, "candidate")
      .replace(/vorlaeufig/g, "provisional")
      .replace(/abgelehnt/g, "rejected")
      .replace(/Gruen/g, "green")
      .replace(/gruen/g, "green")
      .replace(/Gelb/g, "yellow")
      .replace(/gelb/g, "yellow")
      .replace(/Rot/g, "red")
      .replace(/rot/g, "red");
  }
  return source
    .replace(/Farbbaum/g, "arbre couleur")
    .replace(/Baumstruktur/g, "arborescence")
    .replace(/Entscheidungsbaum/g, "arbre de decision")
    .replace(/Lichtkurven/g, "courbes de lumiere")
    .replace(/Rohkandidaten/g, "candidats bruts")
    .replace(/Kandidaten/g, "candidats")
    .replace(/Kandidat/g, "candidat")
    .replace(/vorlaeufig/g, "provisoire")
    .replace(/abgelehnt/g, "rejete")
    .replace(/Gruen/g, "vert")
    .replace(/gruen/g, "vert")
    .replace(/Gelb/g, "jaune")
    .replace(/gelb/g, "jaune")
    .replace(/Rot/g, "rouge")
    .replace(/rot/g, "rouge");
}

export function setText(selector, value) {
  const node = document.querySelector(selector);
  if (node) node.textContent = value;
}

export function setTitle(selector, value) {
  const node = document.querySelector(selector);
  if (node) node.title = value;
}

export function setLegendText(selector, value) {
  const node = document.querySelector(selector);
  if (!node) return;
  const dot = node.querySelector(".dot");
  if (!dot) {
    node.textContent = value;
    return;
  }
  const dotHtml = dot.outerHTML;
  node.innerHTML = dotHtml + " " + value;
}
