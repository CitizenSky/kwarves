import { state, mapZoom, analytics, tessMission, ADMIN_USER, ADMIN_PASSWORD, emptyAnalyticsStore, ensureCountryBucket, saveAnalyticsStore, loadSelfFilterPreference, applyMapZoom, setAdminLoggedIn, setupGlobalAnalytics, loadTessCompareCollapsed, collapseButtonState, updateMapZoomLabel, loadSelectedCardCollapsed, SELECTED_CARD_COLLAPSE_KEY } from './state.js';
import { t, setLanguage, setText, setTitle, setLegendText, buildTessScheduleState, formatNumber, currentLocale, projectFlowStepsI18n, projectLevelsI18n, projectScripts, localizeScriptText, localizeScriptLevel } from './i18n.js';
import { els, data, points2d, DASHBOARD_UI_VERSION, numericBucket, chartRows, matrixStatusBucket, expectedTransits } from './dataLoader.js';
import { renderCurveFilterCounts } from './components/lightcurveView.js';
import { draw2dMap } from './components/starMap2D.js';
import { init3dMap, update3dData, resize3d } from './components/starMap3D.js';
import { renderTable, renderTopCandidates, renderFollowupCandidates, renderVisitorKpis, renderKpis, filteredCandidates, publicCandidatePool, publicVisibleCandidates, setFollowupCollapsed } from './components/candidateList.js';
import { renderSelected, renderYellowReasonPanel } from './components/candidateCard.js';
import { renderMatrixStats, renderVisitorTimeline, renderLabelLegend } from './components/matrixView.js';
import { renderCurves } from './components/lightcurveView.js';
import { renderTess, drawTessSector2d, updateTessSector3dData, initTessSector3d, resizeTessSector3d, setTessCompareCollapsed } from './components/tessMissionControl.js';
import { renderAdmin } from './components/followupPanel.js';
import { showToast, openNotifications, closeNotifications, initPanelCollapseControls, renderNotifications, renderNotificationBadge, setPanelCollapsed } from './ui.js';
import { renderStatRows } from './logic/renderHelpers.js';
import { currentMapNoticeText } from './logic/colorFor.js';
import { startAnalyticsTracking, finalizeAnalyticsSession, setSelfFilterEnabled } from './analytics.js';

let visitorCharts = [];

export function setNavButtonActive(panelId) {
  document.querySelectorAll("[data-nav-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.navTarget === panelId);
  });
}

export function scrollToPanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  if (panel.classList.contains("is-collapsed")) {
    setPanelCollapsed(panelId, false, true);
  }
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function updateDate() {
  const dateStr = new Intl.DateTimeFormat(currentLocale(), {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date());
  document.getElementById("dateLabel").textContent = dateStr;
  const dashDate = document.getElementById("dashboardDateLabel");
  if (dashDate) dashDate.textContent = dateStr;
}

export function selectCandidate(candidate, source = "table") {
  state.selected = candidate;
  renderSelected();
  renderYellowReasonPanel();
  renderTable();
  draw2dMap();
  update3dSelection();
  renderTess();
  const curve = data.lightcurveCandidates.find((item) => item.tic === candidate.tic);
  if (curve && source !== "curve") {
    state.selectedCurve = curve;
    if (!curveMatchesFilter(curve, state.curveFilter)) {
      state.curveFilter = "all";
      document.querySelectorAll("[data-curve-filter]").forEach((button) => {
        button.classList.toggle("active", button.dataset.curveFilter === state.curveFilter);
      });
    }
    renderCurves(false, true);
    setPanelCollapsed("curvesPanel", false, true);
  }
}

export function renderAll() {
  updateMapZoomLabel();
  renderKpis();
  renderVisitorKpis();
  renderLabelLegend();
  renderTopCandidates();
  renderVisitorTimeline();
  renderYellowReasonPanel();
  renderMatrixStats();
  renderTree();
  renderDocs();
  renderTess();
  renderAdmin();
  renderSelected();
  renderTable();
  renderCurveFilterCounts();
  renderCurves(false);
  renderNotificationBadge();
  draw2dMap();
  update3dData();
  renderVisitorCharts();
  if (window.lucide) window.lucide.createIcons();
}

export function renderVisitorCharts() {
  const statsPanel = document.getElementById("statisticsPanel");
  if (statsPanel?.classList.contains("is-collapsed")) {
    visitorCharts.forEach((chart) => chart.destroy());
    visitorCharts = [];
    return;
  }
  const chartDefs = [
    ["chartEvidence", chartRows(["0-39", "40-59", "60-74", "75-89", "90-100"], (c) => numericBucket(c.evidenceScore, [{ label: "0-39", min: 0, max: 40 }, { label: "40-59", min: 40, max: 60 }, { label: "60-74", min: 60, max: 75 }, { label: "75-89", min: 75, max: 90 }, { label: "90-100", min: 90, max: 101 }]))],
    ["chartTransits", chartRows(["0-2", "3-4", "5-9", "10-19", "20+"], (c) => numericBucket(expectedTransits(c), [{ label: "0-2", min: 0, max: 3 }, { label: "3-4", min: 3, max: 5 }, { label: "5-9", min: 5, max: 10 }, { label: "10-19", min: 10, max: 20 }, { label: "20+", min: 20, max: 9999 }]))],
    ["chartDistance", chartRows(["0-25", "25-50", "50-75", "75-100", "100-150", "150+"], (c) => numericBucket(c.distance, [{ label: "0-25", min: 0, max: 25 }, { label: "25-50", min: 25, max: 50 }, { label: "50-75", min: 50, max: 75 }, { label: "75-100", min: 75, max: 100 }, { label: "100-150", min: 100, max: 150 }, { label: "150+", min: 150, max: 9999 }]))],
    ["chartHz", chartRows(["ZU_HEISS", "OPT_HZ_INNEN", "KONSERVATIVE_HZ", "OPT_HZ_AUSSEN", "ZU_KALT"], (c) => c.hz || "ZU_HEISS")],
    ["chartLabels", chartRows(["SPC_STRONG", "SPC", "SPC_ART", "NEEDS_MORE_DATA", "EB_RISK", "REJECTED", "IGNORE"], matrixStatusBucket)],
    ["chartSectors", chartRows(["0", "1", "2", "3-4", "5+"], (c) => numericBucket(c.matrixSectors ?? c.observedSectorCount ?? 0, [{ label: "0", min: 0, max: 1 }, { label: "1", min: 1, max: 2 }, { label: "2", min: 2, max: 3 }, { label: "3-4", min: 3, max: 5 }, { label: "5+", min: 5, max: 9999 }]))]
  ];
  document.querySelectorAll(".chart-fallback").forEach((node) => node.remove());
  if (!window.Chart) {
    chartDefs.forEach(([id, rows]) => {
      const canvas = document.getElementById(id);
      if (!canvas) return;
      const wrap = document.createElement("div");
      wrap.className = "chart-fallback";
      wrap.innerHTML = renderStatRows(rows);
      canvas.replaceWith(wrap);
    });
    return;
  }
  visitorCharts.forEach((chart) => chart.destroy());
  visitorCharts = [];
  chartDefs.forEach(([id, rows]) => {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    visitorCharts.push(new Chart(canvas, {
      type: "bar",
      data: {
        labels: rows.map((row) => row.label),
        datasets: [{ data: rows.map((row) => row.count), backgroundColor: "#16846f", borderRadius: 5 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        resizeDelay: 120,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    }));
  });
}

export function renderTree() {
  els.tree.innerHTML = data.tree.map((node) => `
    <article class="tree-node">
      <div class="tree-node-main">
        <div class="tree-icon"><i data-lucide="git-branch"></i></div>
        <div>
          <h3>${node.title}</h3>
          <p class="muted">${node.description}</p>
        </div>
      </div>
      <div class="tree-children">
        ${node.children.map((child) => `
          <div class="tree-child">
            <strong>${child.label}<span>${formatNumber(child.count)}</span></strong>
            <span>${child.meaning}</span>
          </div>
        `).join("")}
      </div>
    </article>
  `).join("");
  if (window.lucide) window.lucide.createIcons();
}

export function renderDocs() {
  const flowSteps = projectFlowStepsI18n[state.lang] || projectFlowStepsI18n.de;
  const levels = projectLevelsI18n[state.lang] || projectLevelsI18n.de;

  els.docsFlow.innerHTML = flowSteps
    .map((step) => `<span class="docs-step">${step}</span>`)
    .join("");

  els.docsLevels.innerHTML = levels
    .map((level) => `
      <article class="docs-level">
        <strong>${level.name}</strong>
        <p>${level.text}</p>
        ${level.details ? `<ul>${level.details.map((detail) => `<li>${detail}</li>`).join("")}</ul>` : ""}
      </article>
    `)
    .join("");

  els.docsScriptRows.innerHTML = projectScripts
    .map((item) => `
      <tr>
        <td><span class="script-id">${item.script}</span></td>
        <td>${localizeScriptText(item.does)}</td>
        <td>${localizeScriptText(item.why)}</td>
        <td>${localizeScriptLevel(item.level)}</td>
      </tr>
    `)
    .join("");
}

export function applyLanguageToUi() {
  document.documentElement.lang = state.lang;
  document.title = t("app_title");

  const labels = state.lang === "en"
    ? {
      brandSub: "Planethunting",
      navAria: "Dashboard sections",
      eyebrow: "Exoplanet Candidate Explorer",
      treeTitle: "Decision Tree",
      treeSub: "From first color to next action.",
      treeRefresh: "Refresh tree",
      mapTitle: "2D/3D Star Map",
      mapSub: "Project points: color = status, depth = distance, larger 2D markers = better SNR. Click to select candidates.",
      mapSelected: "Selected candidate (white ring/point)",
      mapObserved: "Observed sectors so far",
      mapNext: "Next observation / recheck",
      mapVisible: "Visible points after filter",
      mapLc: "Light curves with PNG",
      mapData: "Data timestamp",
      tessCompareTitle: "3D TESS Sector Map",
      tessMiniSelected: "selected candidate",
      tessMiniHistory: "sector history",
      tessMiniOverlap: "Year-8 overlap",
      tessMiniCurrent: "current/next mission sector",
      tessMiniCoverage: "candidates with sector history",
      selectedCurveTitle: "Show light curve",
      tessPanelTitle: "TESS Mission and Sectors",
      tessPanelSub: "Live orientation: current sector, next planning, and sector arrangement.",
      tessRefresh: "Refresh TESS section",
      tessKpiCurrent: "Current sector",
      tessKpiWindow: "Time window",
      tessKpiTotal: "Numbered sectors",
      tessKpiPrime: "Prime mission",
      tessNoticeStatus: "Status today:",
      tessNoticeYear8: "Year 8 structure:",
      tessNoticeGeometry: "Geometry:",
      tessTableSector: "Sector",
      tessTableStart: "Start",
      tessTableEnd: "End",
      tessTableStatus: "Status",
      tessTableArrangement: "Arrangement",
      tessSource1: "HEASARC sector windows",
      tessSource2: "MIT Year 8 plan",
      curvesTitle: "Light Curves",
      curvesSub: "All candidates are selectable on the left; the combined curve appears on the right.",
      curveSearch: "Search light curve",
      curveOpenCandidate: "Mark candidate",
      tableTitle: "Candidate Matrix",
      tableSub: "Public matrix view lists candidates by visible risk color. ExoFOP readiness is shown only in the restricted review area.",
      tableHeaders: ["TIC", "Evidence", "HZ", "Distance", "Next Step"],
      docsTitle: "Project Logic and Scripts",
      docsSub: "How each level checks candidates, which scripts support it, and why the evidence remains provisional.",
      docsRefresh: "Refresh docs",
      docsScriptsTitle: "Python Scripts",
      docsScriptsSub: "Technical script overview. Tap to expand; tap the sticky header again to collapse.",
      docsScriptsClose: "Collapse scripts",
      docsHeaders: ["Script", "What does it do?", "Why useful?", "Level / Area"],
      legalTitle: "Legal and Notes",
      legalSub: "Project status, responsibility, and privacy notes.",
      adminTitle: "Restricted ExoFOP Review",
      adminSub: "Login-protected candidate list for possible ExoFOP upload preparation.",
      adminRefresh: "Refresh admin",
      adminLoginTitle: "Login",
      adminLoginSub: "Access for ExoFOP review, upload preparation, and internal statistics.",
      adminUser: "Username",
      adminPass: "Password",
      adminLoginBtn: "Login",
      adminReset: "Reset statistics",
      adminLogout: "Logout",
      adminGlobal: "Global analytics:",
      adminDetails: "Details:",
      adminDashboard: "Dashboard:",
      adminSelfFilter: "Self filter:",
      adminViews: "Local views",
      adminSessions: "Local sessions",
      adminAvg: "Local avg. duration",
      adminLast: "Local last visit",
      adminCountry: "Current country:",
      adminSource: "Source:",
      adminNoteLabel: "Note:",
      adminHint: "Local fallback only. These rows are not GoatCounter data; use GoatCounter for global public analytics.",
      adminCountryHeaders: ["Country", "Local views", "Local sessions", "Local duration", "Avg/local session"],
      aboutHtml: `
        <h3>Scientific Notice</h3>
        <p>Kwarves is an independent citizen-science project analyzing publicly available TESS and Gaia data.</p>
        <p>Displayed candidates, ratings, and classifications are generated automatically and are partly in an early research stage.</p>
        <p>Not all available observations, follow-up measurements, archive data, or scientific publications are fully included.</p>
        <p>New data can lead to re-evaluation, confirmation, or rejection of a candidate.</p>
        <p>Displayed results are not a confirmation of an exoplanet and do not claim completeness or scientific finality.</p>
      `,
      impressumHtml: `
        <h3>Legal Notice</h3>
        <p><strong>Responsible for content:</strong><br />Konrad Gottschalk</p>
        <p>Kwarves is an independent citizen-science project analyzing publicly available astronomical data.</p>
        <p><strong>Contact:</strong><br /><a href="mailto:astroproject725@gmail.com">astroproject725@gmail.com</a></p>
        <p>If you have improvements, ideas, or notes, please send an email or leave a comment.</p>
      `,
      privacyHtml: `
        <h3>Privacy</h3>
        <p>This website uses a dashboard with local browser statistics and optional external audience measurement.</p>
        <p>Analytics data is used only to improve the project and does not replace scientific publication.</p>
      `,
      aboutProjectHtml: `
        <h3>Methodology</h3>
        <p>From Gaia stellar parameters to provisional SPC/SPC_ART classification.</p>
        <p>Gaia provides stellar parameters and distance. TESS provides light curves and sector windows. BLS/TLS searches for periodic transit signals. The Evidence Score rates data coverage and signal quality. SPC means strong planet candidate; SPC_ART means strong candidate with artifact or systematics concern.</p>
        <h3>Notice</h3>
        <p>Kwarves is an independent citizen-science project analyzing publicly available TESS and Gaia data. Displayed results are not a confirmation of an exoplanet and do not claim completeness or scientific finality.</p>
      `
    }
    : state.lang === "fr"
      ? {
        brandSub: "Planethunting",
        navAria: "Sections du dashboard",
        eyebrow: "Exoplanet Candidate Explorer",
        treeTitle: "Arbre de Decision",
        treeSub: "De la premiere couleur a l'action suivante.",
        treeRefresh: "Actualiser l'arbre",
        mapTitle: "Carte Stellaire 2D/3D",
        mapSub: "Points du projet: couleur = statut, profondeur = distance, grands points 2D = meilleur SNR. Cliquez pour selectionner un candidat.",
        mapSelected: "Candidat selectionne (anneau/point blanc)",
        mapObserved: "Secteurs deja observes",
        mapNext: "Prochaine observation / reverification",
        mapVisible: "Points visibles apres filtre",
        mapLc: "Courbes avec PNG",
        mapData: "Horodatage des donnees",
        tessCompareTitle: "Carte 3D des Secteurs TESS",
        tessMiniSelected: "candidat selectionne",
        tessMiniHistory: "historique secteurs",
        tessMiniOverlap: "recouvrement Year-8",
        tessMiniCurrent: "secteur mission actuel/prochain",
        tessMiniCoverage: "candidats avec historique secteurs",
        selectedCurveTitle: "Afficher la courbe",
        tessPanelTitle: "Mission TESS et Secteurs",
        tessPanelSub: "Orientation en direct: secteur actuel, planification suivante et organisation des secteurs.",
        tessRefresh: "Actualiser la section TESS",
        tessKpiCurrent: "Secteur actuel",
        tessKpiWindow: "Fenetre temporelle",
        tessKpiTotal: "Secteurs numerotes",
        tessKpiPrime: "Mission prime",
        tessNoticeStatus: "Statut aujourd'hui:",
        tessNoticeYear8: "Structure Year 8:",
        tessNoticeGeometry: "Geometrie:",
        tessTableSector: "Secteur",
        tessTableStart: "Debut",
        tessTableEnd: "Fin",
        tessTableStatus: "Statut",
        tessTableArrangement: "Disposition",
        tessSource1: "Fenetres secteurs HEASARC",
        tessSource2: "Planification MIT Year 8",
        curvesTitle: "Courbes de Lumiere",
        curvesSub: "Tous les candidats sont selectionnables a gauche; la courbe combinee apparait a droite.",
        curveSearch: "Rechercher une courbe",
        curveOpenCandidate: "Marquer le candidat",
        tableTitle: "Matrice Candidats",
        tableSub: "La matrice publique liste les candidats par couleur de risque visible. La readiness ExoFOP reste dans la zone restreinte.",
        tableHeaders: ["TIC", "Evidence", "HZ", "Distance", "Etape suivante"],
        docsTitle: "Logique Projet et Scripts",
        docsSub: "Comment chaque niveau verifie les candidats, quels scripts le soutiennent, et pourquoi l'evidence reste provisoire.",
        docsRefresh: "Actualiser la doc",
        docsScriptsTitle: "Scripts Python",
        docsScriptsSub: "Vue technique des scripts. Toucher pour ouvrir; retoucher l'en-tete fixe pour refermer.",
        docsScriptsClose: "Refermer les scripts",
        docsHeaders: ["Script", "Que fait-il?", "Pourquoi utile?", "Niveau / Zone"],
        legalTitle: "Mentions Legales et Notes",
        legalSub: "Statut du projet, responsabilite et notes de confidentialite.",
        adminTitle: "Review ExoFOP restreint",
        adminSub: "Liste protegee pour preparer de possibles depots ExoFOP.",
        adminRefresh: "Actualiser admin",
        adminLoginTitle: "Connexion",
        adminLoginSub: "Acces au review ExoFOP, a la preparation d'upload et aux statistiques internes.",
        adminUser: "Nom d'utilisateur",
        adminPass: "Mot de passe",
        adminLoginBtn: "Connexion",
        adminReset: "Reinitialiser statistiques",
        adminLogout: "Deconnexion",
        adminGlobal: "Analytics global:",
        adminDetails: "Details:",
        adminDashboard: "Dashboard:",
        adminSelfFilter: "Filtre propre:",
        adminViews: "Vues locales",
        adminSessions: "Sessions locales",
        adminAvg: "Duree moyenne locale",
        adminLast: "Derniere visite locale",
        adminCountry: "Pays actuel:",
        adminSource: "Source:",
        adminNoteLabel: "Note:",
        adminHint: "Fallback local uniquement. Ces lignes ne sont pas des donnees GoatCounter; utilisez GoatCounter pour les statistiques publiques globales.",
        adminCountryHeaders: ["Pays", "Vues locales", "Sessions locales", "Duree locale", "Moyenne/session locale"],
        aboutHtml: `
          <h3>Note Scientifique</h3>
          <p>Kwarves est un projet citizen-science independant pour l'analyse de donnees TESS et Gaia publiquement disponibles.</p>
          <p>Les candidats, evaluations et classifications affiches sont generes automatiquement et se trouvent en partie a un stade de recherche precoce.</p>
          <p>Toutes les observations disponibles, mesures de suivi, donnees d'archives ou publications scientifiques ne sont pas prises en compte de facon exhaustive.</p>
          <p>De nouvelles donnees peuvent conduire a une reevaluation, une confirmation ou un rejet d'un candidat.</p>
          <p>Les resultats affiches ne constituent pas une confirmation d'exoplanete et ne pretendent ni a l'exhaustivite ni a une finalite scientifique.</p>
        `,
        impressumHtml: `
          <h3>Mentions Legales</h3>
          <p><strong>Responsable du contenu:</strong><br />Konrad Gottschalk</p>
          <p>Kwarves est un projet citizen-science independant pour l'analyse de donnees astronomiques publiquement disponibles.</p>
          <p><strong>Contact:</strong><br /><a href="mailto:astroproject725@gmail.com">astroproject725@gmail.com</a></p>
          <p>Pour des ameliorations, idees ou remarques, envoyez volontiers un e-mail ou laissez un commentaire.</p>
        `,
        privacyHtml: `
          <h3>Confidentialite</h3>
          <p>Ce site utilise un dashboard avec statistiques locales navigateur et mesure d'audience externe optionnelle.</p>
        <p>Les donnees d'analyse servent uniquement a ameliorer le projet et ne remplacent pas une publication scientifique.</p>
      `,
      aboutProjectHtml: `
        <h3>Methodologie</h3>
        <p>Des parametres stellaires Gaia a la classification provisoire SPC/SPC_ART.</p>
        <p>Gaia fournit les parametres stellaires et la distance. TESS fournit les courbes de lumiere et les fenetres de secteurs. BLS/TLS cherche des signaux de transit periodiques. L'Evidence Score evalue la couverture de donnees et la qualite du signal. SPC signifie candidat planetaire fort; SPC_ART signifie candidat fort avec suspicion d'artefact ou de systematique.</p>
        <h3>Avis</h3>
        <p>Kwarves est un projet citizen-science independant pour l'analyse de donnees TESS et Gaia publiquement disponibles. Les resultats affiches ne constituent pas une confirmation d'exoplanete et ne pretendent ni a l'exhaustivite ni a une finalite scientifique.</p>
      `
      }
      : {
        brandSub: "Planethunting",
        navAria: "Dashboard Bereiche",
        eyebrow: "Exoplanet Candidate Explorer",
        treeTitle: "Baumstruktur der Entscheidung",
        treeSub: "Von der ersten Farbe bis zur naechsten Aktion.",
        treeRefresh: "Baum aktualisieren",
        mapTitle: "2D/3D Sternkarte",
        mapSub: "Punkte aus dem Projekt: Farbe = Status, Tiefe = Entfernung, groessere 2D-Kugeln = bessere SNR. Klicken waehlt Kandidaten aus.",
        mapSelected: "Ausgewaehlter Kandidat (weisser Ring/Punkt)",
        mapObserved: "Bisher beobachtete Sektoren",
        mapNext: "Naechste Beobachtung / Recheck",
        mapVisible: "sichtbare Punkte nach Filter",
        mapLc: "Lichtkurven mit PNG",
        mapData: "Datenstand",
        tessCompareTitle: "3D TESS-Sektorenkarte",
        tessMiniSelected: "ausgewaehlter Kandidat",
        tessMiniHistory: "Sektorhistorie",
        tessMiniOverlap: "Year-8-Abgleich",
        tessMiniCurrent: "aktueller/naechster Mission-Sektor",
        tessMiniCoverage: "Kandidaten mit Sektorhistorie",
        selectedCurveTitle: "Lichtkurve zeigen",
        tessPanelTitle: "TESS Mission und Sektoren",
        tessPanelSub: "Live-Orientierung: aktueller Sektor, naechste Planung und Anordnung der Sektoren.",
        tessRefresh: "TESS-Bereich aktualisieren",
        tessKpiCurrent: "Aktueller Sektor",
        tessKpiWindow: "Zeitfenster",
        tessKpiTotal: "Nummerierte Sektoren",
        tessKpiPrime: "Prime Mission",
        tessNoticeStatus: "Status heute:",
        tessNoticeYear8: "Year 8 Struktur:",
        tessNoticeGeometry: "Geometrie:",
        tessTableSector: "Sektor",
        tessTableStart: "Start",
        tessTableEnd: "Ende",
        tessTableStatus: "Status",
        tessTableArrangement: "Anordnung",
        tessSource1: "HEASARC Sektorzeiten",
        tessSource2: "MIT Year 8 Planung",
        curvesTitle: "Lichtkurven",
        curvesSub: "Alle Kandidaten sind links auswaehlbar; rechts erscheint die kombinierte Kurve.",
        curveSearch: "Lichtkurve suchen",
        curveOpenCandidate: "Kandidat markieren",
        tableTitle: "Candidate Matrix",
        tableSub: "Die oeffentliche Matrix zeigt Kandidaten nach sichtbarer Risikofarbe. ExoFOP-Readiness steht nur im eingeschraenkten Review-Bereich.",
        tableHeaders: ["TIC", "Evidence", "HZ", "Distanz", "N\u00e4chster Schritt"],
        docsTitle: "Projektlogik und Skripte",
        docsSub: "Wie jedes Level Kandidaten prueft, welche Skripte es stuetzen und warum die Evidenz vorlaeufig bleibt.",
        docsRefresh: "Dokuseite aktualisieren",
        docsScriptsTitle: "Python-Skripte",
        docsScriptsSub: "Technische Skriptuebersicht. Antippen zum Oeffnen; den festen Kopf erneut antippen zum Zuklappen.",
        docsScriptsClose: "Skripte zuklappen",
        docsHeaders: ["Skript", "Was macht es?", "Warum sinnvoll?", "Level / Bereich"],
        legalTitle: "Impressum und Hinweise",
        legalSub: "Projektstatus, Verantwortlichkeit und Datenschutz-Hinweise.",
        adminTitle: "Restricted ExoFOP Review",
        adminSub: "Login-geschuetzte Kandidatenliste fuer moegliche ExoFOP-Upload-Vorbereitung.",
        adminRefresh: "Admin aktualisieren",
        adminLoginTitle: "Login",
        adminLoginSub: "Zugang fuer ExoFOP-Review, Upload-Vorbereitung und interne Statistik.",
        adminUser: "Benutzername",
        adminPass: "Passwort",
        adminLoginBtn: "Login",
        adminReset: "Statistik zuruecksetzen",
        adminLogout: "Logout",
        adminGlobal: "Globale Analytics:",
        adminDetails: "Details:",
        adminDashboard: "Dashboard:",
        adminSelfFilter: "Eigenfilter:",
        adminViews: "Lokale Aufrufe",
        adminSessions: "Lokale Sitzungen",
        adminAvg: "Lokale durchschn. Dauer",
        adminLast: "Lokaler letzter Besuch",
        adminCountry: "Aktuelles Land:",
        adminSource: "Quelle:",
        adminNoteLabel: "Hinweis:",
        adminHint: "Nur lokaler Fallback. Diese Zeilen sind keine GoatCounter-Daten; fuer globale oeffentliche Analytics bitte GoatCounter nutzen.",
        adminCountryHeaders: ["Land", "Lokale Aufrufe", "Lokale Sitzungen", "Lokale Dauer", "Durchschnitt/lokale Sitzung"],
        aboutHtml: `
          <h3>Wissenschaftlicher Hinweis</h3>
          <p>Kwarves ist ein unabhaengiges Citizen-Science-Projekt zur Analyse oeffentlich verfuegbarer TESS- und Gaia-Daten.</p>
          <p>Die dargestellten Kandidaten, Bewertungen und Klassifizierungen werden automatisiert erzeugt und befinden sich teilweise in einem fruehen Forschungsstadium.</p>
          <p>Nicht alle verfuegbaren Beobachtungen, Follow-up-Messungen, Archivdaten oder wissenschaftlichen Veroeffentlichungen werden vollstaendig beruecksichtigt.</p>
          <p>Neue Daten koennen zu einer Neubewertung, Bestaetigung oder Ablehnung eines Kandidaten fuehren.</p>
          <p>Die dargestellten Ergebnisse stellen keine Bestaetigung eines Exoplaneten dar und erheben keinen Anspruch auf Vollstaendigkeit oder wissenschaftliche Endgueltigkeit.</p>
        `,
        impressumHtml: `
          <h3>Impressum</h3>
          <p><strong>Verantwortlich fuer den Inhalt:</strong><br />Konrad Gottschalk</p>
          <p>Kwarves ist ein unabhaengiges Citizen-Science-Projekt zur Analyse oeffentlich verfuegbarer astronomischer Daten.</p>
          <p><strong>Kontakt:</strong><br /><a href="mailto:astroproject725@gmail.com">astroproject725@gmail.com</a></p>
          <p>Bei Verbesserungen, Ideen oder Hinweisen gern per E-Mail melden oder einen Kommentar hinterlassen.</p>
        `,
        privacyHtml: `
          <h3>Privacy</h3>
          <p>Diese Webseite nutzt ein Dashboard mit lokalen Browser-Statistiken und optional externer Reichweitenmessung.</p>
        <p>Analysedaten dienen nur der Projektverbesserung und ersetzen keine wissenschaftliche Publikation.</p>
      `,
      aboutProjectHtml: `
        <h3>Methodik</h3>
        <p>Von Gaia-Sternparametern bis zur vorlaeufigen SPC/SPC_ART-Klassifikation.</p>
        <p>Gaia liefert Sternparameter und Distanz. TESS liefert Lichtkurven und Sektorfenster. BLS/TLS sucht periodische Transit-Signale. Der Evidence Score bewertet Datenlage und Signalqualitaet. SPC bedeutet starker Planetenkandidat; SPC_ART bedeutet starker Kandidat mit Artefakt- oder Systematikverdacht.</p>
        <h3>Hinweis</h3>
        <p>Kwarves ist ein unabhaengiges Citizen-Science-Projekt zur Analyse oeffentlich verfuegbarer TESS- und Gaia-Daten. Die dargestellten Ergebnisse stellen keine Bestaetigung eines Exoplaneten dar und erheben keinen Anspruch auf Vollstaendigkeit oder wissenschaftliche Endgueltigkeit.</p>
      `
      };

  const setNav = (panel, text) => {
    setText(`[data-nav-target="${panel}"] span`, text);
    setTitle(`[data-nav-target="${panel}"]`, text);
  };

  document.querySelector(".brand span").textContent = labels.brandSub;
  document.querySelector(".nav").setAttribute("aria-label", labels.navAria);
  setNav("tablePanel", t("nav_kandidaten"));
  setNav("treePanel", t("nav_analyse"));
  setNav("tessPanel", t("nav_tess"));
  setNav("docsPanel", t("nav_projekt"));

  setText(".sidebar-note strong", t("sidebar_rule_title"));
  setText(".sidebar-note span", t("sidebar_rule_text"));
  setText("#refreshData span", t("refresh_data"));
  setTitle("#refreshData", t("refresh_data"));
  setText(".eyebrow", labels.eyebrow);
  setText(".lede", t("lede"));
  setText("#focusHzLabel", t("hz_focus"));
  const aboutContent = document.getElementById("aboutProjectContent");
  if (aboutContent) {
    aboutContent.innerHTML = labels.aboutProjectHtml || "";
  }
  const visitorCopy = state.lang === "en"
    ? {
      introEyebrow: "Citizen-science Exoplanet Screening",
      introClaim: "Independent citizen-science dashboard for TESS/Gaia based exoplanet candidate screening.",
      introText: "We analyze publicly available Gaia and TESS data, filter nearby K dwarfs, and rate possible transit candidates by data quality, signal stability, and habitable-zone context. The matrix does not just collect light-curve dips; it performs multi-stage pre-vetting against artifacts, weak observing windows, and eclipsing-binary risks.",
      disclaimer: "<strong>Transparency:</strong> CitizenSky/Kwarves is an independent citizen-science project. Results are preliminary automated screenings based on public Gaia and TESS data. Candidate classifications are not confirmed planets. The analysis is incomplete and requires manual vetting, additional data, and professional follow-up.",
      statusTitle: "Project Status & Short Logic",
      statusSub: "Candidate state, color code, and follow-up rules at a glance.",
      decisionCards: [
        ["Orange", "Ordinary recheck candidates: interesting, but not follow-up-ready yet."],
        ["Yellow / SPC Prep", "Internal follow-up candidates. Track actively, but not automatically ExoFOP-ready."],
        ["Violet", "HZ focus as an additional marker. Violet does not replace the traffic-light color."],
        ["ExoFOP", "Upload only after strict green release; orange and yellow remain internal."]
      ],
      methodTitle: "Methodology",
      methodSub: "From Gaia stellar parameters to provisional SPC/SPC_ART classification.",
      methodNotice: "Gaia provides stellar parameters and distance. TESS provides light curves and sector windows. BLS/TLS searches for periodic transit signals. The Evidence Score rates data coverage and signal quality. SPC means strong planet candidate; SPC_ART means strong candidate with artifact or systematics concern.",
      methodSteps: [
        ["Gaia DR3", "Stellar parameters, distance, and astrometry."],
        ["K-dwarf filter", "Structure nearby K, G, and M stars."],
        ["TESS sectors", "Check light curves and observing windows."],
        ["BLS/TLS search", "Search for periodic transit signals."],
        ["Evidence Score", "Rate data coverage and signal quality."],
        ["SPC / SPC_ART", "Separate strong candidates from artifact risks."],
        ["HZ review", "Prioritize habitable-zone context and follow-up."]
      ],
      labelTitle: "Candidate Labels",
      labelSub: "Short reading guide for the most important Kwarves status values.",
      labelHeaders: ["Label", "Meaning"],
      topTitle: "Top Candidates",
      topSub: "Compact decision list. Details open in the candidate profile.",
      topHeaders: ["Rank", "TIC", "Distance ly", "Period days", "HZ class", "Evidence", "Label", "Next step"],
      followupTitle: "Follow-up Candidates",
      followupSub: "Internal follow-up cases, separated from ordinary orange.",
      statsTitle: "Statistics Plots",
      statsSub: "Distributions from existing matrix and candidate fields.",
      chartTitles: ["Evidence Score", "Transit count", "Distance", "HZ classes", "Label distribution", "TESS sectors"],
      signalTitle: "Data Coverage vs. Signal",
      signalSub: "Why strong signals can still remain yellow when the data basis is uncertain.",
      signalCells: [
        ["", "Weak signal", "Medium signal", "Strong signal"],
        ["Good data", ["Good + weak", "Observe / recheck", "Signal is not yet enough for follow-up."], ["Good + medium", "SPC_ART / review", "Manual vetting decides."], ["Good + strong", "SPC / follow-up", "Best public candidate list."]],
        ["Medium data", ["Medium + weak", "Low recheck", "New sectors may help."], ["Medium + medium", "SPC_ART", "Artifact or systematics risk remains open."], ["Medium + strong", "SPC_ART / more data", "Not green without stable data coverage."]],
        ["Poor data", ["Poor + weak", "Ignore / low priority", "No robust evidence."], ["Poor + medium", "NEEDS_MORE_TESS_DATA", "Too little coverage."], ["Poor + strong", "SPC_ART / more data needed", "Strong signal, but not clean enough yet."]]
      ],
      timelineTitle: "TESS Observation Timeline",
      timelineSub: "Prepared view for sector history, Year-8 hits, and recheck planning.",
      timelineNotice: "Year-8 hit does not mean the target was not observed for eight years. It means the candidate position overlaps with expected or planned Year-8 TESS coverage geometry and should be checked against official sector products. The geometry is currently a robust mission overview, not an exact sky projection.",
      footerMini: "Independent citizen-science project. No official NASA/ESA affiliation. Data sources: Gaia DR3, TESS/MAST. Non-commercial research and learning project."
    }
    : state.lang === "fr"
      ? {
        introEyebrow: "Screening exoplanetaire citizen-science",
        introClaim: "Dashboard citizen-science independant pour la preselection de candidats exoplanetes avec TESS/Gaia.",
        introText: "Nous analysons des donnees Gaia et TESS publiques, filtrons des naines K proches et evaluons les candidats de transit possibles selon la qualite des donnees, la stabilite du signal et le contexte de zone habitable. La matrice ne collecte pas seulement des creux de courbe de lumiere; elle applique un pre-vetting multi-etapes contre les artefacts, les fenetres d'observation faibles et les risques de binaires a eclipses.",
        disclaimer: "<strong>Transparence:</strong> CitizenSky/Kwarves est un projet citizen-science independant. Les resultats sont des screenings automatises preliminaires bases sur les donnees publiques Gaia et TESS. Les classifications ne sont pas des planetes confirmees. L'analyse est incomplete et requiert un vetting manuel, des donnees supplementaires et un suivi professionnel.",
        statusTitle: "Statut du projet & logique courte",
        statusSub: "Etat des candidats, code couleur et regles de suivi en bref.",
        decisionCards: [
          ["Orange", "Candidats de reverification ordinaires: interessants, mais pas encore prets pour le suivi."],
          ["Jaune / SPC Prep", "Candidats internes de suivi. A suivre activement, mais pas automatiquement ExoFOP-ready."],
          ["Violet", "Focus HZ comme marqueur additionnel. Violet ne remplace pas la couleur principale."],
          ["ExoFOP", "Depot seulement apres validation verte stricte; orange et jaune restent internes."]
        ],
        methodTitle: "Methodologie",
        methodSub: "Des parametres stellaires Gaia a la classification provisoire SPC/SPC_ART.",
        methodNotice: "Gaia fournit les parametres stellaires et la distance. TESS fournit les courbes de lumiere et les fenetres de secteurs. BLS/TLS cherche des signaux de transit periodiques. L'Evidence Score evalue la couverture de donnees et la qualite du signal. SPC signifie candidat planetaire fort; SPC_ART signifie candidat fort avec suspicion d'artefact ou de systematique.",
        methodSteps: [
          ["Gaia DR3", "Parametres stellaires, distance et astrometrie."],
          ["Filtre naines K", "Structurer les etoiles K, G et M proches."],
          ["Secteurs TESS", "Verifier courbes de lumiere et fenetres d'observation."],
          ["Recherche BLS/TLS", "Chercher des signaux de transit periodiques."],
          ["Evidence Score", "Evaluer couverture des donnees et qualite du signal."],
          ["SPC / SPC_ART", "Separer candidats forts et risques d'artefacts."],
          ["Revue HZ", "Prioriser zone habitable et suivi."]
        ],
        labelTitle: "Labels des candidats",
        labelSub: "Guide court pour les principaux statuts Kwarves.",
        labelHeaders: ["Label", "Signification"],
        topTitle: "Top candidats",
        topSub: "Liste compacte pour decider. Les details s'ouvrent dans le profil candidat.",
        topHeaders: ["Rang", "TIC", "Distance al", "Periode jours", "Classe HZ", "Evidence", "Label", "Prochaine etape"],
        followupTitle: "Candidats de suivi",
        followupSub: "Cas internes de suivi, separes de l'orange ordinaire.",
        statsTitle: "Graphiques statistiques",
        statsSub: "Distributions issues des champs matrice et candidats existants.",
        chartTitles: ["Evidence Score", "Nombre de transits", "Distance", "Classes HZ", "Distribution labels", "Secteurs TESS"],
        signalTitle: "Donnees vs signal",
        signalSub: "Pourquoi un signal fort peut rester jaune lorsque la base de donnees est incertaine.",
        signalCells: [
          ["", "Signal faible", "Signal moyen", "Signal fort"],
          ["Bonnes donnees", ["Bonnes + faible", "Observer / recheck", "Signal pas encore suffisant pour le suivi."], ["Bonnes + moyen", "SPC_ART / revue", "Le vetting manuel decide."], ["Bonnes + fort", "SPC / suivi", "Meilleure liste publique de candidats."]],
          ["Donnees moyennes", ["Moyen + faible", "Low recheck", "De nouveaux secteurs peuvent aider."], ["Moyen + moyen", "SPC_ART", "Risque artefact ou systematique ouvert."], ["Moyen + fort", "SPC_ART / plus de donnees", "Pas vert sans donnees stables."]],
          ["Mauvaises donnees", ["Mauvais + faible", "Ignorer / basse priorite", "Pas d'evidence robuste."], ["Mauvais + moyen", "NEEDS_MORE_TESS_DATA", "Couverture trop faible."], ["Mauvais + fort", "SPC_ART / plus de donnees", "Signal fort, mais pas encore propre."]]
        ],
        timelineTitle: "Timeline d'observation TESS",
        timelineSub: "Vue preparee pour historique des secteurs, hits Year-8 et planification recheck.",
        timelineNotice: "Un hit Year-8 ne signifie pas que la cible n'a pas ete observee pendant huit ans. Cela signifie que la position du candidat recoupe la geometrie de couverture TESS Year-8 attendue ou planifiee et doit etre verifiee avec les produits officiels des secteurs. La geometrie est actuellement une vue mission robuste, pas une projection celeste exacte.",
        footerMini: "Projet citizen-science independant. Aucune affiliation officielle NASA/ESA. Sources: Gaia DR3, TESS/MAST. Projet non commercial de recherche et d'apprentissage."
      }
      : {
        introEyebrow: "Citizen-Science Exoplaneten-Screening",
        introClaim: "Unabhaengiges Citizen-Science-Dashboard fuer die TESS/Gaia-basierte Vorpruefung von Exoplaneten-Kandidaten.",
        introText: "Wir analysieren oeffentlich verfuegbare Gaia- und TESS-Daten, filtern nahe K-Zwerge und bewerten moegliche Transit-Kandidaten nach Datenqualitaet, Signalstabilitaet und Habitable-Zone-Kontext. Die Matrix sammelt nicht nur Lichtkurven-Dips, sondern nutzt eine mehrstufige Vorpruefung gegen Artefakte, schwache Datenfenster und EB-Risiken.",
        disclaimer: "<strong>Transparenz:</strong> CitizenSky/Kwarves ist ein unabhaengiges Citizen-Science-Projekt. Ergebnisse sind vorlaeufige automatisierte Screenings auf Basis oeffentlicher Gaia- und TESS-Daten. Kandidatenklassifikationen sind keine bestaetigten Planeten. Die Analyse ist unvollstaendig und erfordert manuelles Vetting, weitere Daten und professionelles Follow-up.",
        statusTitle: "Projektstatus & Kurzlogik",
        statusSub: "Kandidatenlage, Farbcode und Follow-up-Regeln auf einen Blick.",
        decisionCards: [
          ["Orange", "Normale Recheck-Kandidaten: interessant, aber noch nicht Follow-up-ready."],
          ["Gelb / SPC Prep", "Interne Follow-up-Kandidaten. Aktiv weiterverfolgen, aber nicht automatisch ExoFOP-ready."],
          ["Violett", "HZ-Fokus als Zusatzmarker. Violett ersetzt keine Ampelfarbe."],
          ["ExoFOP", "Upload erst bei strenger gruener Freigabe; orange und gelb bleiben intern."]
        ],
        methodTitle: "Methodik",
        methodSub: "Von Gaia-Sternparametern bis zur vorlaeufigen SPC/SPC_ART-Klassifikation.",
        methodNotice: "Gaia liefert Sternparameter und Distanz. TESS liefert Lichtkurven und Sektorfenster. BLS/TLS sucht periodische Transit-Signale. Der Evidence Score bewertet Datenlage und Signalqualitaet. SPC bedeutet starker Planetenkandidat; SPC_ART bedeutet starker Kandidat mit Artefakt- oder Systematikverdacht.",
        methodSteps: [
          ["Gaia DR3", "Sternparameter, Distanz und Astrometrie."],
          ["K-Zwerg Filter", "Nahe K-, G- und M-Sterne strukturieren."],
          ["TESS-Sektoren", "Lichtkurven und Datenfenster pruefen."],
          ["BLS/TLS-Suche", "Periodische Transit-Signale suchen."],
          ["Evidence Score", "Datenlage und Signalqualitaet bewerten."],
          ["SPC / SPC_ART", "Starke Kandidaten von Artefakt-Risiken trennen."],
          ["HZ-Review", "Habitable-Zone-Kontext und Follow-up priorisieren."]
        ],
        labelTitle: "Kandidatenlabels",
        labelSub: "Kurze Leseregel fuer die wichtigsten Kwarves-Statuswerte.",
        labelHeaders: ["Label", "Bedeutung"],
        topTitle: "Top Kandidaten",
        topSub: "Kompakte Entscheidungsliste. Details stehen im Kandidatenprofil.",
        topHeaders: ["Rang", "TIC", "Distanz ly", "Periode Tage", "HZ-Klasse", "Evidence", "Label", "Naechster Schritt"],
        followupTitle: "Follow-up Kandidaten",
        followupSub: "Alle internen Follow-up-Faelle, getrennt von normalem Orange.",
        statsTitle: "Statistik-Plots",
        statsSub: "Verteilungen aus den vorhandenen Matrix- und Kandidatenfeldern.",
        chartTitles: ["Evidence Score", "Transitanzahl", "Distanz", "HZ-Klassen", "Label-Verteilung", "TESS-Sektoren"],
        signalTitle: "Datenlage vs. Signal",
        signalSub: "Warum starke Signale trotzdem gelb bleiben koennen, wenn die Datenlage unsicher ist.",
        signalCells: [
          ["", "Signal schwach", "Signal mittel", "Signal stark"],
          ["Daten gut", ["Gute Daten + schwach", "Beobachten / Recheck", "Signal reicht noch nicht fuer Follow-up."], ["Gute Daten + mittel", "SPC_ART / Review", "Manuelle Pruefung entscheidet."], ["Gute Daten + stark", "SPC / Follow-up", "Beste oeffentliche Kandidatenliste."]],
          ["Daten mittel", ["Mittel + schwach", "Low Recheck", "Neue Sektoren koennen helfen."], ["Mittel + mittel", "SPC_ART", "Artefakt- oder Systematikrisiko offen."], ["Mittel + stark", "SPC_ART / mehr Daten", "Nicht gruen ohne stabile Datenlage."]],
          ["Daten schlecht", ["Schlecht + schwach", "Ignorieren / niedrige Prioritaet", "Keine belastbare Evidenz."], ["Schlecht + mittel", "NEEDS_MORE_TESS_DATA", "Zu wenig Abdeckung."], ["Schlecht + stark", "SPC_ART / mehr Daten noetig", "Starkes Signal, aber noch nicht sicher."]]
        ],
        timelineTitle: "TESS-Beobachtungsplan",
        timelineSub: "Vorbereitung fuer Sektorverlauf, Year-8-Treffer und Recheck-Planung.",
        timelineNotice: "Ein Year-8-Treffer bedeutet nicht, dass das Ziel acht Jahre lang nicht beobachtet wurde. Er bedeutet, dass die Kandidatenposition mit erwarteter oder geplanter TESS-Year-8-Abdeckungsgeometrie ueberlappt und gegen offizielle Sektorprodukte geprueft werden sollte. Die Geometrie ist aktuell eine robuste Missionsansicht, aber keine exakte Himmelsprojektion.",
        footerMini: "Unabhaengiges Citizen-Science-Projekt. Keine offizielle NASA/ESA-Verbindung. Datenquellen: Gaia DR3, TESS/MAST. Keine kommerzielle Nutzung; Forschungs- und Lernprojekt."
      };
  setText("#introEyebrow", visitorCopy.introEyebrow);
  setText("#introClaim", visitorCopy.introClaim);
  setText("#introText", visitorCopy.introText);
  const introDisclaimerEl = document.getElementById("introDisclaimer");
  if (introDisclaimerEl) introDisclaimerEl.innerHTML = visitorCopy.disclaimer;
  setText("#visitorStatusTitle", visitorCopy.statusTitle);
  setText("#visitorStatusSub", visitorCopy.statusSub);
  const decisionSummaryEl = document.getElementById("decisionSummary");
  if (decisionSummaryEl) decisionSummaryEl.innerHTML = visitorCopy.decisionCards.map(([title, text]) => `
    <article class="decision-card">
      <strong>${title}</strong>
      <p>${text}</p>
    </article>
  `).join("");
  setText("#methodTitle", visitorCopy.methodTitle);
  setText("#methodSub", visitorCopy.methodSub);
  setText("#methodNotice", visitorCopy.methodNotice);
  document.getElementById("methodSteps").innerHTML = visitorCopy.methodSteps.map((step, index) => `
    <article class="method-step"><span>${index + 1}</span><strong>${step[0]}</strong><p class="mini">${step[1]}</p></article>
  `).join("");
  setText("#labelLegendTitle", visitorCopy.labelTitle);
  setText("#labelLegendSub", visitorCopy.labelSub);
  document.getElementById("labelLegendHeader").innerHTML = visitorCopy.labelHeaders.map((value) => `<th>${value}</th>`).join("");
  setText("#topCandidatesTitle", visitorCopy.topTitle);
  setText("#topCandidatesSub", visitorCopy.topSub);
  document.getElementById("topCandidatesHead").innerHTML = `<tr>${visitorCopy.topHeaders.map((value) => `<th>${value}</th>`).join("")}</tr>`;
  setText("#followupCandidatesTitle", visitorCopy.followupTitle);
  setText("#followupCandidatesSub", visitorCopy.followupSub);
  setText("#statisticsTitle", visitorCopy.statsTitle);
  setText("#statisticsSub", visitorCopy.statsSub);
  document.querySelectorAll("#statisticsPanel .chart-card h3").forEach((node, index) => {
    node.textContent = visitorCopy.chartTitles[index] || node.textContent;
  });
  setText("#signalMatrixTitle", visitorCopy.signalTitle);
  setText("#signalMatrixSub", visitorCopy.signalSub);
  document.getElementById("signalMatrixGrid").innerHTML = `
    <div class="matrix-axis"></div>
    ${visitorCopy.signalCells[0].slice(1).map((value) => `<div class="matrix-axis">${value}</div>`).join("")}
    ${visitorCopy.signalCells.slice(1).map((row) => `
      <div class="matrix-axis">${row[0]}</div>
      ${row.slice(1).map((cell, index) => {
        const cls = row[0].includes("schlecht") || row[0].includes("Poor") || row[0].includes("Mauvais")
          ? (index === 0 ? "red" : "yellow")
          : (row[0].includes("gut") || row[0].includes("Good") || row[0].includes("Bonnes")) && index === 2
            ? "green"
            : "yellow";
        return `<article class="matrix-cell ${cls}"><span>${cell[0]}</span><strong>${cell[1]}</strong><p class="mini">${cell[2]}</p></article>`;
      }).join("")}
    `).join("")}
  `;
  setText("#observationTimelineTitle", visitorCopy.timelineTitle);
  setText("#observationTimelineSub", visitorCopy.timelineSub);
  setText("#observationTimelineNotice", visitorCopy.timelineNotice);
  setText("#footerMini", visitorCopy.footerMini);
  const yellowCopy = {
    de: {
      title: "Warum ist dieser Kandidat gelb?",
      sub: "Gelb bedeutet nicht schlecht: wissenschaftlich interessant, aber nicht sauber genug fuer automatisches Gruen.",
      selected: "Ausgewaehlter gelber Kandidat",
      matrix: "Wert vs. Unsicherheitsgrund"
    },
    en: {
      title: "Why is this candidate yellow?",
      sub: "Yellow does not mean bad: scientifically interesting, but not clean enough for automatic green.",
      selected: "Selected yellow candidate",
      matrix: "Value vs. uncertainty reason"
    },
    fr: {
      title: "Pourquoi ce candidat est-il jaune ?",
      sub: "Jaune ne signifie pas mauvais : scientifiquement interessant, mais pas assez propre pour le vert automatique.",
      selected: "Candidat jaune selectionne",
      matrix: "Valeur vs raison d'incertitude"
    }
  }[state.lang] || {};
  setText("#yellowReasonTitle", yellowCopy.title);
  setText("#yellowReasonSub", yellowCopy.sub);
  setText("#yellowSelectedTitle", yellowCopy.selected);
  setText("#yellowMatrixTitle", yellowCopy.matrix);
  setTitle("#showHints", t("hint_button_title"));
  document.getElementById("globalSearch").placeholder = t("search_placeholder");
  document.getElementById("curveSearch").placeholder = labels.curveSearch;

  const langSwitch = document.getElementById("langSwitch");
  if (langSwitch) {
    langSwitch.setAttribute("aria-label", t("lang_switch_label"));
    const langTitles = {
      de: state.lang === "fr" ? "Allemand" : state.lang === "en" ? "German" : "Deutsch",
      en: state.lang === "fr" ? "Anglais" : state.lang === "en" ? "English" : "Englisch",
      fr: state.lang === "fr" ? "Francais" : state.lang === "en" ? "French" : "Franzoesisch"
    };
    langSwitch.querySelectorAll("[data-lang]").forEach((button) => {
      button.classList.toggle("active", button.dataset.lang === state.lang);
      const targetLang = button.dataset.lang || "de";
      button.title = langTitles[targetLang] || targetLang.toUpperCase();
      button.setAttribute("aria-label", langTitles[targetLang] || targetLang.toUpperCase());
    });
  }

  setText(".kpis article:nth-child(1) .card-top span", t("kpi_total"));
  setText(".kpis article:nth-child(2) .card-top span", t("kpi_green"));
  setText(".kpis article:nth-child(3) .card-top span", t("kpi_yellow"));
  setText(".kpis article:nth-child(4) .card-top span", t("kpi_spc_prep"));
  setText(".kpis article:nth-child(5) .card-top span", t("kpi_red"));
  setText(".kpis article:nth-child(6) .card-top span", t("kpi_violet"));
  document.querySelector(".kpis article:nth-child(1) .metric-line").innerHTML = `<i data-lucide="folder-tree"></i> ${t("kpi_total_sub")}`;
  document.querySelector(".kpis article:nth-child(2) .metric-line").innerHTML = `<i data-lucide="arrow-up-right"></i> ${t("kpi_green_sub")}`;
  document.querySelector(".kpis article:nth-child(3) .metric-line").innerHTML = `<i data-lucide="hourglass"></i> ${t("kpi_yellow_sub")}`;
  document.querySelector(".kpis article:nth-child(4) .metric-line").innerHTML = `<i data-lucide="list-checks"></i> ${t("kpi_spc_prep_sub")}`;
  document.querySelector(".kpis article:nth-child(5) .metric-line").innerHTML = `<i data-lucide="ban"></i> ${t("kpi_red_sub")}`;
  document.querySelector(".kpis article:nth-child(6) .metric-line").innerHTML = `<i data-lucide="sun-medium"></i> ${t("kpi_violet_sub")}`;

  setText("#treePanel h2", labels.treeTitle);
  setText("#treePanel .panel-subtitle", labels.treeSub);
  setTitle("#refreshTree", labels.treeRefresh);

  setText("#mapPanel h2", labels.mapTitle);
  setText("#mapPanel > .panel-header .panel-subtitle", labels.mapSub);
  setText('[data-color-filter="all"]', t("filter_all"));
  setText('[data-color-filter="green"]', t("filter_green"));
  setText('[data-color-filter="yellow"]', t("filter_yellow"));
  setText('[data-color-filter="spc-prep"]', t("filter_spc_prep"));
  setText('[data-color-filter="red"]', t("filter_red"));
  setText('[data-color-filter="violet"]', t("filter_violet"));
  setLegendText("#mapPanel .map-note .legend-item:nth-child(1)", t("map_legend_green"));
  setLegendText("#mapPanel .map-note .legend-item:nth-child(2)", t("map_legend_yellow"));
  setLegendText("#mapPanel .map-note .legend-item:nth-child(3)", t("map_legend_spc_prep"));
  setLegendText("#mapPanel .map-note .legend-item:nth-child(4)", t("map_legend_red"));
  setLegendText("#mapPanel .map-note .legend-item:nth-child(5)", t("map_legend_violet"));
  setText("#mapPanel .map-note .legend-item:nth-child(6)", t("map_legend_selected"));
  setLegendText("#mapPanel .map-note .legend-item:nth-child(7)", t("map_legend_sun"));
  setText("#mapPanel .map-side .notice", currentMapNoticeText());
  setText("#mapPanel .map-status:nth-of-type(1) span", labels.mapSelected);
  setText("#mapPanel .map-status:nth-of-type(2) span", labels.mapObserved);
  setText("#mapPanel .map-status:nth-of-type(3) span", labels.mapNext);
  if (!state.selected) {
    setText("#mapCoverageStatus", t("map_status_hint"));
  }
  setText("#mapPanel .map-stat:nth-of-type(1) span", labels.mapVisible);
  setText("#mapPanel .map-stat:nth-of-type(2) span", labels.mapLc);
  setText("#mapPanel .map-stat:nth-of-type(3) span", labels.mapData);

  setText("#tessCompareCard h3", labels.tessCompareTitle);
  setText("#tessCompareCard h3 + p", t("tess_notice_symbolic"));
  setLegendText("#tessPanel .tess-sector-note .legend-item:nth-child(1)", t("tess_label_candidate_sector"));
  setLegendText("#tessPanel .tess-sector-note .legend-item:nth-child(2)", t("tess_label_observed"));
  setLegendText("#tessPanel .tess-sector-note .legend-item:nth-child(3)", t("tess_label_planned"));
  setLegendText("#tessPanel .tess-sector-note .legend-item:nth-child(4)", t("tess_label_background"));
  setText(".tess-compare-side .tess-mini-stat:nth-child(1) span", labels.tessMiniSelected);
  setText(".tess-compare-side .tess-mini-stat:nth-child(2) span", labels.tessMiniHistory);
  setText(".tess-compare-side .tess-mini-stat:nth-child(3) span", labels.tessMiniOverlap);
  setText(".tess-compare-side .tess-mini-stat:nth-child(4) span", labels.tessMiniCurrent);
  setText(".tess-compare-side .tess-mini-stat:nth-child(5) span", labels.tessMiniCoverage);
  setText(".coverage-timeline h4", t("timeline_title"));
  setText(".coverage-timeline .timeline-row:nth-child(2) .timeline-label", t("timeline_observed"));
  setText(".coverage-timeline .timeline-row:nth-child(3) .timeline-label", t("timeline_planned"));
  setText(".coverage-timeline .timeline-row:nth-child(4) .timeline-label", t("timeline_next"));
  setText(".coverage-timeline .timeline-row:nth-child(5) .timeline-label", t("timeline_status"));
  setText(".map-selected-head h3", t("selected_title"));
  setText(".map-selected-head p", t("selected_subtitle"));
  setTitle("#showSelectedCurve", labels.selectedCurveTitle);

  setText("#tessPanel h2", labels.tessPanelTitle);
  setText("#tessPanel .panel-subtitle", labels.tessPanelSub);
  const aboutPanelTitle = document.querySelector("#aboutProjectPanel .panel-header h2");
  if (aboutPanelTitle) aboutPanelTitle.textContent = t("about_project_title");
  setTitle("#refreshTess", labels.tessRefresh);
  setText("#tessPanel .tess-kpi:nth-child(1) span", labels.tessKpiCurrent);
  setText("#tessPanel .tess-kpi:nth-child(2) span", labels.tessKpiWindow);
  setText("#tessPanel .tess-kpi:nth-child(3) span", labels.tessKpiTotal);
  setText("#tessPanel .tess-kpi:nth-child(4) span", labels.tessKpiPrime);
  const tessNotice = document.querySelector("#tessPanel .panel-body .notice");
  if (tessNotice) {
    tessNotice.innerHTML = `<strong>${labels.tessNoticeStatus}</strong> <span id="tessCurrentStatus">-</span><br />
      <strong>${labels.tessNoticeYear8}</strong> <span id="tessYear8Info">-</span><br />
      <strong>${labels.tessNoticeGeometry}</strong> <span id="tessGeometryInfo">-</span>`;
    els.tessCurrentStatus = document.getElementById("tessCurrentStatus");
    els.tessYear8Info = document.getElementById("tessYear8Info");
    els.tessGeometryInfo = document.getElementById("tessGeometryInfo");
  }
  document.querySelectorAll("#tessPanel thead th").forEach((th, index) => {
    th.textContent = labels.tessTableSector;
    if (index === 1) th.textContent = labels.tessTableStart;
    if (index === 2) th.textContent = labels.tessTableEnd;
    if (index === 3) th.textContent = labels.tessTableStatus;
    if (index === 4) th.textContent = labels.tessTableArrangement;
  });
  setText("#tessPanel .tess-sources a:nth-child(1)", labels.tessSource1);
  setText("#tessPanel .tess-sources a:nth-child(2)", labels.tessSource2);

  setText("#curvesPanel h2", labels.curvesTitle);
  setText('[data-curve-filter="all"]', t("curves_filter_all"));
  setText('[data-curve-filter="violet"]', t("curves_filter_violet"));
  setText('[data-curve-filter="green"]', t("curves_filter_green"));
  setText('[data-curve-filter="spc-prep"]', t("curves_filter_spc_prep"));
  setText('[data-curve-filter="orange"]', t("curves_filter_orange"));
  setText('[data-curve-filter="red"]', t("curves_filter_red"));
  renderCurveFilterCounts();
  setTitle("#openCurveCandidate", labels.curveOpenCandidate);

  setText("#tablePanel h2", labels.tableTitle);
  setText("#tablePanel .panel-subtitle", labels.tableSub);
  document.querySelectorAll("#tablePanel thead th").forEach((th, index) => {
    th.textContent = labels.tableHeaders[index] || th.textContent;
  });

  setText("#docsPanel h2", labels.docsTitle);
  setText("#docsPanel .panel-subtitle", labels.docsSub);
  setTitle("#refreshDocs", labels.docsRefresh);
  setText("#docsScriptsTitle", labels.docsScriptsTitle);
  setText("#docsScriptsSub", labels.docsScriptsSub);
  setText("#docsScriptsCloseLabel", labels.docsScriptsClose);
  document.querySelectorAll("#docsPanel .docs-table thead th").forEach((th, index) => {
    th.textContent = labels.docsHeaders[index] || th.textContent;
  });

  setText("#impressumPanel h2", labels.legalTitle);
  setText("#impressumPanel .panel-subtitle", labels.legalSub);
  const about = document.getElementById("aboutSection");
  const impressum = document.getElementById("impressumSection");
  const privacy = document.getElementById("privacySection");
  if (about) about.innerHTML = labels.aboutHtml;
  if (impressum) impressum.innerHTML = labels.impressumHtml;
  if (privacy) privacy.innerHTML = labels.privacyHtml;

  setText("#adminPanel h2", labels.adminTitle);
  setText("#adminPanel .panel-subtitle", labels.adminSub);
  setTitle("#refreshAdmin", labels.adminRefresh);
  setText("#adminLoginCard h3", labels.adminLoginTitle);
  setText("#adminLoginCard .muted", labels.adminLoginSub);
  setText("#adminUserLabel", labels.adminUser);
  setText("#adminPassLabel", labels.adminPass);
  setText("#adminLoginButtonLabel", labels.adminLoginBtn);
  const adminResetBtn = document.getElementById("adminResetStats");
  if (adminResetBtn) adminResetBtn.innerHTML = `<i data-lucide="eraser"></i> ${labels.adminReset}`;
  const adminLogoutBtn = document.getElementById("adminLogout");
  if (adminLogoutBtn) adminLogoutBtn.innerHTML = `<i data-lucide="log-out"></i> ${labels.adminLogout}`;
  const adminGlobalNotice = document.querySelector("#adminStatsWrap .notice");
  if (adminGlobalNotice) {
    adminGlobalNotice.innerHTML = `<strong>${labels.adminGlobal}</strong> <span id="adminGlobalStatus">-</span><br />
      <strong>${labels.adminDetails}</strong> <span id="adminGlobalDetails">-</span><br />
      <strong>${labels.adminDashboard}</strong> <a id="adminGlobalDashboardLink" href="#" target="_blank" rel="noopener noreferrer">-</a><br />
      <strong>${labels.adminSelfFilter}</strong> <span id="adminSelfFilterStatus">-</span>`;
    els.adminGlobalStatus = document.getElementById("adminGlobalStatus");
    els.adminGlobalDetails = document.getElementById("adminGlobalDetails");
    els.adminGlobalDashboardLink = document.getElementById("adminGlobalDashboardLink");
    els.adminSelfFilterStatus = document.getElementById("adminSelfFilterStatus");
  }
  setText("#adminStatsWrap .admin-kpi:nth-child(1) span", labels.adminViews);
  setText("#adminStatsWrap .admin-kpi:nth-child(2) span", labels.adminSessions);
  setText("#adminStatsWrap .admin-kpi:nth-child(3) span", labels.adminAvg);
  setText("#adminStatsWrap .admin-kpi:nth-child(4) span", labels.adminLast);
  const adminCountryNotice = document.querySelectorAll("#adminStatsWrap .notice")[1];
  if (adminCountryNotice) {
    adminCountryNotice.innerHTML = `<strong>${labels.adminCountry}</strong> <span id="adminCurrentCountry">-</span><br />
      <strong>${labels.adminSource}</strong> <span id="adminCountrySource">-</span><br />
      <strong>${labels.adminNoteLabel}</strong> ${labels.adminHint}`;
    els.adminCurrentCountry = document.getElementById("adminCurrentCountry");
    els.adminCountrySource = document.getElementById("adminCountrySource");
  }
  document.querySelectorAll("#adminCountryTable thead th").forEach((th, index) => {
    th.textContent = labels.adminCountryHeaders[index] || th.textContent;
  });

  setText(".site-footer-alert", t("footer_alert"));
  setText('.site-footer-links a[href="#aboutSection"]', t("footer_about"));
  setText('.site-footer-links a[href="#impressumSection"]', t("footer_impressum"));
  setText('.site-footer-links a[href="#privacySection"]', t("footer_privacy"));
  setText('.site-footer-links a[href*="github.com"]', t("footer_github"));

  tessMission.year8Description = t("year8_description");
  tessMission.geometryDescription = t("geometry_description");
  if (!analytics.countryResolved) {
    analytics.countrySource = t("admin_country_source_unknown");
    if (!analytics.countryName || analytics.countryCode === "UN") {
      analytics.countryName = t("table_country_unknown");
    }
  }
  setTessCompareCollapsed(Boolean(els.tessCompareCard?.classList.contains("is-collapsed")), false);
  document.querySelectorAll(".panel-collapse-toggle").forEach((button) => {
    collapseButtonState(button, button.getAttribute("aria-expanded") === "false");
  });

  window.lucide?.createIcons();
}

document.querySelectorAll("[data-nav-target]").forEach((button) => {
  button.addEventListener("click", () => {
    const target = button.dataset.navTarget;
    setNavButtonActive(target);
    scrollToPanel(target);
  });
});

document.querySelectorAll("#langSwitch [data-lang]").forEach((button) => {
  button.addEventListener("click", () => {
    const lang = button.dataset.lang;
    if (!lang || lang === state.lang) return;
    setLanguage(lang, true);
  });
});

document.querySelectorAll("[data-doc-anchor]").forEach((link) => {
  link.addEventListener("click", (event) => {
    const targetId = link.dataset.docAnchor;
    const panelTarget = link.dataset.panelTarget || "docsPanel";
    if (!targetId) return;
    event.preventDefault();
    setNavButtonActive(panelTarget);
    scrollToPanel(panelTarget);
    window.requestAnimationFrame(() => {
      const node = document.getElementById(targetId);
      if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    history.replaceState(null, "", `#${targetId}`);
  });
});

document.querySelectorAll("[data-color-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    state.colorFilter = button.dataset.colorFilter;
    document.querySelectorAll("[data-color-filter]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    draw2dMap();
    update3dData();
    renderTable();
  });
});

document.querySelectorAll("[data-map-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.mapMode = button.dataset.mapMode;
    document.querySelectorAll("[data-map-mode]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    els.mapFrame.classList.toggle("mode-3d", state.mapMode === "3d");
    if (state.mapMode === "3d") {
      init3dMap();
      resize3d();
    }
  });
});

document.querySelectorAll("[data-map-zoom]").forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.mapZoom;
    if (action === "in") applyMapZoom(mapZoom * 1.25);
    if (action === "out") applyMapZoom(mapZoom / 1.25);
    if (action === "reset") applyMapZoom(1);
  });
});

els.mapFrame.addEventListener("wheel", (event) => {
  event.preventDefault();
  const direction = event.deltaY < 0 ? 1.12 : 1 / 1.12;
  applyMapZoom(mapZoom * direction);
}, { passive: false });

document.querySelectorAll("[data-tess-map-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.tessMapMode = button.dataset.tessMapMode;
    document.querySelectorAll("[data-tess-map-mode]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    els.tessSectorFrame.classList.toggle("mode-3d", state.tessMapMode === "3d");
    if (state.tessMapMode === "3d") {
      initTessSector3d();
      resizeTessSector3d();
    } else {
      const tessState = buildTessScheduleState();
      drawTessSector2d(tessState);
      updateTessSector3dData(tessState);
    }
  });
});

if (els.tessCompareToggle) {
  els.tessCompareToggle.addEventListener("click", () => {
    const card = els.tessCompareCard;
    const collapsed = card ? !card.classList.contains("is-collapsed") : false;
    setTessCompareCollapsed(collapsed, true);
  });
}

if (els.toggleSelectedCard && els.selectedCardSection) {
  els.toggleSelectedCard.addEventListener("click", () => {
    const section = els.selectedCardSection;
    const collapsed = !section.classList.contains("is-collapsed");
    section.classList.toggle("is-collapsed", collapsed);
    els.toggleSelectedCard.setAttribute("aria-expanded", collapsed ? "false" : "true");
    try {
      localStorage.setItem(SELECTED_CARD_COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch (_) {}
  });
}

document.querySelectorAll("[data-curve-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    state.curveFilter = button.dataset.curveFilter;
    document.querySelectorAll("[data-curve-filter]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderCurves();
  });
});

document.querySelectorAll("[data-table-limit]").forEach((button) => {
  button.addEventListener("click", () => {
    state.tableLimit = button.dataset.tableLimit === "all" ? "all" : Number(button.dataset.tableLimit);
    document.querySelectorAll("[data-table-limit]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderTable();
  });
});

document.querySelectorAll("[data-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    const sortBy = button.dataset.sort;
    if (state.sortBy === sortBy) {
      state.sortOrder = state.sortOrder === "desc" ? "asc" : "desc";
    } else {
      state.sortBy = sortBy;
      state.sortOrder = "desc";
    }
    document.querySelectorAll("[data-sort]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderTable();
  });
});

els.globalSearch.addEventListener("input", () => {
  renderTable();
  renderAdmin();
  draw2dMap();
  update3dData();
});

els.curveSearch.addEventListener("input", () => renderCurves());

els.rows.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-tic]");
  if (!row) return;
  const candidate = data.candidates.find((item) => item.tic === Number(row.dataset.tic));
  if (candidate) selectCandidate(candidate);
});

els.topCandidateRows.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-profile-tic]");
  if (!row) return;
  const candidate = data.candidates.find((item) => item.tic === Number(row.dataset.profileTic));
  if (candidate) {
    selectCandidate(candidate, "profile");
    scrollToPanel("mapPanel");
  }
});

els.followupCandidateRows.addEventListener("click", (event) => {
  const row = event.target.closest("[data-followup-tic]");
  if (!row) return;
  const candidate = data.candidates.find((item) => item.tic === Number(row.dataset.followupTic));
  if (candidate) {
    selectCandidate(candidate, "followup");
    scrollToPanel("mapPanel");
  }
});

els.toggleFollowupList?.addEventListener("click", () => {
  const panel = document.querySelector(".followup-subpanel");
  setFollowupCollapsed(!panel?.classList.contains("is-collapsed"));
});

els.curveList.addEventListener("click", (event) => {
  const item = event.target.closest("[data-curve-tic]");
  if (!item) return;
  const candidate = data.lightcurveCandidates.find((entry) => entry.tic === Number(item.dataset.curveTic));
  if (!candidate) return;
  state.selectedCurve = candidate;
  selectCandidate(candidate, "curve");
  renderCurves(false, true);
});

els.matrixStats.addEventListener("click", (event) => {
  const button = event.target.closest("[data-stat-tic]");
  if (!button) return;
  const candidate = data.candidates.find((item) => item.tic === Number(button.dataset.statTic));
  if (candidate) selectCandidate(candidate, "stats");
});

els.notificationList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-notification-tic]");
  if (!button) return;
  const candidate = data.candidates.find((item) => item.tic === Number(button.dataset.notificationTic));
  if (candidate) {
    selectCandidate(candidate, "notification");
    closeNotifications();
    scrollToPanel("mapPanel");
  }
});

els.mapCanvas.addEventListener("click", (event) => {
  const rect = els.mapCanvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  let best = null;
  let bestDistance = Infinity;
  points2d.forEach((point) => {
    const distance = Math.hypot(point.x - x, point.y - y);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  });
  if (best && bestDistance <= Math.max(14, best.radius + 4)) {
    selectCandidate(best.candidate, "map");
  }
});

document.getElementById("showSelectedCurve").addEventListener("click", () => {
  const curve = data.lightcurveCandidates.find((item) => state.selected && item.tic === state.selected.tic);
  if (curve) {
    state.selectedCurve = curve;
    renderCurves(false, true);
    setNavButtonActive("curvesPanel");
    document.getElementById("curvesPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    showToast(t("toast_no_curve_for_candidate"));
  }
});

document.getElementById("openCurveCandidate").addEventListener("click", () => {
  if (state.selectedCurve) selectCandidate(state.selectedCurve, "curve");
});

document.getElementById("focusHz").addEventListener("click", () => {
  state.colorFilter = "violet";
  document.querySelectorAll("[data-color-filter]").forEach((item) => item.classList.remove("active"));
  document.querySelector('[data-color-filter="violet"]').classList.add("active");
  renderTable();
  draw2dMap();
  update3dData();
  showToast(t("toast_filter_hz"));
});

document.getElementById("refreshData").addEventListener("click", () => {
  showToast(t("toast_refresh_data"));
});

document.getElementById("refreshTree").addEventListener("click", () => {
  renderTree();
  window.lucide?.createIcons();
  showToast(t("toast_tree_updated"));
});

document.getElementById("refreshDocs").addEventListener("click", () => {
  renderDocs();
  showToast(t("toast_docs_updated"));
});

document.getElementById("docsScriptsClose")?.addEventListener("click", () => {
  const scriptsWindow = document.getElementById("docsScriptsWindow");
  if (!scriptsWindow) return;
  scriptsWindow.open = false;
  scriptsWindow.scrollIntoView({ behavior: "smooth", block: "center" });
});

document.getElementById("refreshTess").addEventListener("click", () => {
  renderTess();
  showToast(t("toast_tess_updated"));
});

els.adminLoginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const user = String(els.adminUserInput.value || "").trim();
  const pass = String(els.adminPassInput.value || "");
  if (user === ADMIN_USER && pass === ADMIN_PASSWORD) {
    setAdminLoggedIn(true);
    els.adminPassInput.value = "";
    els.adminLoginHint.textContent = "";
    renderAdmin();
    window.lucide?.createIcons();
    showToast(t("toast_admin_login_ok"));
  } else {
    els.adminLoginHint.textContent = t("login_failed");
    showToast(t("toast_admin_login_fail"));
  }
});

document.getElementById("adminLogout").addEventListener("click", () => {
  setAdminLoggedIn(false);
  renderAdmin();
  showToast(t("toast_admin_logout"));
});

els.adminToggleSelfFilter.addEventListener("click", () => {
  const next = !analytics.selfFilterEnabled;
  setSelfFilterEnabled(next);
  showToast(next
    ? t("toast_filter_self_on")
    : t("toast_filter_self_off"));
});

document.getElementById("adminResetStats").addEventListener("click", () => {
  if (!window.confirm(t("confirm_reset_stats"))) return;
  analytics.store = emptyAnalyticsStore();
  analytics.sessionStartedAt = Date.now();
  analytics.sessionClosed = false;
  analytics.sessionCounted = false;
  analytics.sessionCountCountryCode = "UN";
  if (!analytics.selfFilterEnabled) {
    analytics.store.totalViews = 1;
    analytics.store.totalSessions = 1;
    analytics.store.lastVisitAt = new Date().toISOString();
    const bucket = ensureCountryBucket(analytics.countryCode, analytics.countryName);
    bucket.views += 1;
    bucket.sessions += 1;
    analytics.sessionCounted = true;
    analytics.sessionCountCountryCode = analytics.countryCode || "UN";
  }
  saveAnalyticsStore();
  renderAdmin();
  showToast(t("toast_stats_reset"));
});

document.getElementById("refreshAdmin").addEventListener("click", () => {
  renderAdmin();
  showToast(t("toast_admin_refresh"));
});

document.getElementById("showHints").addEventListener("click", () => {
  openNotifications();
});

document.getElementById("closeNotifications").addEventListener("click", closeNotifications);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeNotifications();
});

window.addEventListener("resize", () => {
  window.requestAnimationFrame(() => {
    draw2dMap();
    resize3d();
    const tessState = buildTessScheduleState();
    drawTessSector2d(tessState);
    updateTessSector3dData(tessState);
    resizeTessSector3d();
  });
});

window.addEventListener("pagehide", () => {
  finalizeAnalyticsSession();
});

initPanelCollapseControls();
setPanelCollapsed("tablePanel", false, true);
setTessCompareCollapsed(loadTessCompareCollapsed(), false);
(function initSelectedCardCollapse() {
  const collapsed = loadSelectedCardCollapsed();
  if (els.selectedCardSection) {
    els.selectedCardSection.classList.toggle("is-collapsed", collapsed);
  }
  if (els.toggleSelectedCard) {
    els.toggleSelectedCard.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
})();
analytics.selfFilterEnabled = loadSelfFilterPreference();
applyLanguageToUi();
setupGlobalAnalytics();
updateDate();
startAnalyticsTracking();
state.selected = publicCandidatePool()[0] || publicVisibleCandidates()[0] || null;
state.selectedCurve = data.lightcurveCandidates.find((item) => state.selected && item.tic === state.selected.tic) || data.lightcurveCandidates[0] || null;
renderAll();
document.getElementById("loadingOverlay")?.classList.add("hidden");
state.sortBy = "evidence";
state.sortOrder = "desc";
if (state.tessMapMode === "3d") {
  initTessSector3d();
}
setInterval(() => {
  updateDate();
  renderTess();
  renderAdmin();
}, 30000);
