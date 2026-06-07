import { state, tessMission, tessYear8SectorSet, tessSectorLayout, TESS_COMPARE_COLLAPSE_KEY } from '../state.js';
import { t, formatNumber, formatDate, formatDateRange, formatMonthYear, formatSectorList, daysDiff, normalizeSectorList, buildTessScheduleState } from '../i18n.js';
import { els, data, buildCandidateCoverageModel, tessPoints2d, tessThree } from '../dataLoader.js';
import { setupCanvas } from './starMap2D.js';

export function tessSectorVisual(sector, observedSet, plannedSet, currentSector, nextSector) {
  if (sector === currentSector) return "current";
  if (sector === nextSector) return "next";
  const observed = observedSet.has(sector);
  const planned = plannedSet.has(sector);
  if (observed && planned) return "candidate";
  if (planned) return "planned";
  if (observed) return "observed";
  return "base";
}

export function tessSectorColor(visualType) {
  if (visualType === "current") return "#f2c968";
  if (visualType === "next") return "#e39f3a";
  if (visualType === "candidate") return "#2ca98c";
  if (visualType === "planned") return "#efba4a";
  if (visualType === "observed") return "#5c8cf6";
  return "#5c6872";
}

export function localizeTessArrangement(value) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  if (state.lang === "de") return raw;
  if (state.lang === "en") {
    return raw
      .replace(/Suedpol/g, "South pole")
      .replace(/Grad Roll\/Shift/g, "deg roll/shift");
  }
  return raw
    .replace(/Suedpol/g, "Pole sud")
    .replace(/Grad Roll\/Shift/g, "deg rotation/decalage");
}

export function drawTessSector2d(scheduleState) {
  if (!els.tessSectorCanvas) return;
  const current = scheduleState.current || null;
  const next = scheduleState.next || null;
  const { ctx, width, height } = setupCanvas(els.tessSectorCanvas);
  tessPoints2d.length = 0;
  ctx.clearRect(0, 0, width, height);
  const gradient = ctx.createRadialGradient(width * 0.5, height * 0.5, 18, width * 0.5, height * 0.5, width * 0.75);
  gradient.addColorStop(0, "#152226");
  gradient.addColorStop(1, "#0b1215");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(255,255,255,0.11)";
  ctx.lineWidth = 1;
  for (let cycle = 0; cycle <= 8; cycle += 1) {
    const radius = 50 + cycle * 22;
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, radius, 0, Math.PI * 2);
    ctx.stroke();
  }

  const coverage = buildCandidateCoverageModel(scheduleState);
  const currentSector = current ? current.sector : null;
  const nextSector = next ? next.sector : null;
  const observedSet = new Set(coverage.observed);
  const plannedSet = new Set((coverage.planned || []).map((item) => item.sector));

  tessSectorLayout.forEach((entry) => {
    const visual = tessSectorVisual(entry.sector, observedSet, plannedSet, currentSector, nextSector);
    const x = width / 2 + entry.x * width * 0.22;
    const y = height / 2 + (entry.z * 0.82 + entry.y * 0.18) * height * 0.28;
    const radius =
      visual === "current" ? 5.2 :
      visual === "candidate" ? 4.7 :
      visual === "planned" ? 4.1 :
      visual === "observed" ? 3.9 : 3.3;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = tessSectorColor(visual);
    ctx.globalAlpha = visual === "base" ? 0.6 : 0.95;
    ctx.fill();
    if (visual === "current" || visual === "candidate") {
      ctx.beginPath();
      ctx.arc(x, y, radius + 2.2, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = 1.1;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    tessPoints2d.push({ x, y, radius, sector: entry.sector });
  });

  ctx.fillStyle = "rgba(255,255,255,0.74)";
  ctx.font = "700 12px Inter, system-ui, sans-serif";
  ctx.fillText(t("chart_legend_tess"), 12, 22);
}

export function initTessSector3d() {
  if (!window.THREE || tessThree.ready || !els.tessSector3d) return;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  els.tessSector3d.innerHTML = "";
  els.tessSector3d.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(56, 1, 0.1, 120);
  camera.position.set(0, 0.65, 5.6);
  scene.add(new THREE.AmbientLight(0xffffff, 0.95));

  const root = new THREE.Group();
  scene.add(root);

  const meshes = new Map();
  const sphereGeometry = new THREE.SphereGeometry(0.052, 10, 10);
  tessSectorLayout.forEach((entry) => {
    const material = new THREE.MeshBasicMaterial({ color: 0x5c6872 });
    const mesh = new THREE.Mesh(sphereGeometry, material);
    mesh.position.set(entry.x * 1.72, entry.y * 1.35, entry.z * 1.72);
    mesh.userData = { sector: entry.sector };
    meshes.set(entry.sector, mesh);
    root.add(mesh);
  });

  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(0.078, 18, 18),
    new THREE.MeshBasicMaterial({ color: 0xf4c96d })
  );
  root.add(sun);

  Object.assign(tessThree, { ready: true, renderer, scene, camera, root, meshes, rotation: 0 });
  const tessState = buildTessScheduleState();
  updateTessSector3dData(tessState);
  resizeTessSector3d();
  animateTessSector3d();
}

export function updateTessSector3dData(scheduleState) {
  if (!tessThree.ready) return;
  const coverage = buildCandidateCoverageModel(scheduleState);
  const current = scheduleState.current || null;
  const next = scheduleState.next || null;
  const currentSector = current ? current.sector : null;
  const nextSector = next ? next.sector : null;
  const observedSet = new Set(coverage.observed);
  const plannedSet = new Set((coverage.planned || []).map((item) => item.sector));
  tessSectorLayout.forEach((entry) => {
    const visual = tessSectorVisual(entry.sector, observedSet, plannedSet, currentSector, nextSector);
    const color = tessSectorColor(visual);
    const mesh = tessThree.meshes.get(entry.sector);
    if (!mesh) return;
    mesh.material.color.set(color);
    mesh.material.opacity = visual === "base" ? 0.66 : 0.98;
    mesh.material.transparent = true;
    const scale =
      visual === "current" ? 1.55 :
      visual === "candidate" ? 1.42 :
      visual === "planned" ? 1.3 :
      visual === "observed" ? 1.23 : 1;
    mesh.scale.set(scale, scale, scale);
  });
}

export function resizeTessSector3d() {
  if (!tessThree.ready || !els.tessSector3d) return;
  const rect = els.tessSector3d.getBoundingClientRect();
  tessThree.renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false);
  tessThree.camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height);
  tessThree.camera.updateProjectionMatrix();
}

export function animateTessSector3d() {
  if (!tessThree.ready) return;
  tessThree.rotation += 0.0021;
  tessThree.root.rotation.y = tessThree.rotation;
  tessThree.root.rotation.x = -0.31;
  tessThree.renderer.render(tessThree.scene, tessThree.camera);
  requestAnimationFrame(animateTessSector3d);
}

export function renderMapCoverageSummary(coverage) {
  if (!els.mapSelectedTic) return;
  const candidate = coverage.candidate;
  els.mapSelectedTic.textContent = candidate ? `TIC ${candidate.tic}` : "-";
  els.mapObservedSectors.textContent = coverage.observed.length
    ? formatSectorList(coverage.observed, 10)
    : t("unknown");
  els.mapNextRecheck.textContent = coverage.observed.length
    ? coverage.nextObservationText
    : (candidate && candidate.nextRecheck ? `DB-Recheck: ${candidate.nextRecheck}` : t("not_computable_missing_history"));

  if (!candidate) {
    els.mapCoverageStatus.textContent = t("no_candidate_selected");
    return;
  }
  if (coverage.statusKey === "green") {
    els.mapCoverageStatus.textContent = t("map_status_green");
    return;
  }
  if (coverage.statusKey === "blue") {
    els.mapCoverageStatus.textContent = t("map_status_blue");
    return;
  }
  if (coverage.statusKey === "yellow") {
    els.mapCoverageStatus.textContent = t("map_status_yellow");
    return;
  }
  if (coverage.statusKey === "gray") {
    els.mapCoverageStatus.textContent = t("map_status_red");
    return;
  }
  els.mapCoverageStatus.textContent = t("map_status_missing");
}

export function renderTessSectorSummary(scheduleState) {
  if (!els.tessMatchSelectedTic) return;
  const withSectorHistory = (data.candidates || []).filter((item) => normalizeSectorList(item.observedSectors).length > 0).length;
  const coverage = buildCandidateCoverageModel(scheduleState);
  const candidate = coverage.candidate;
  els.tessMatchSelectedTic.textContent = candidate ? `TIC ${candidate.tic}` : "-";
  els.tessMatchSectorList.textContent = coverage.observed.length ? formatSectorList(coverage.observed, 12) : t("unknown");
  els.tessMatchYear8Overlap.textContent = coverage.observed.length
    ? (coverage.overlapYear8.length
      ? t("match_year8_count", { count: coverage.overlapYear8.length, list: formatSectorList(coverage.overlapYear8, 8) })
      : t("match_year8_none"))
    : t("not_computable_missing_history");
  els.tessMatchCoverage.textContent = `${withSectorHistory}/${formatNumber((data.candidates || []).length)}`;
  if (scheduleState.current) {
    els.tessMatchCurrent.textContent = t("match_current_running", { sector: scheduleState.current.sector });
  } else if (scheduleState.next) {
    els.tessMatchCurrent.textContent = t("match_current_next", { sector: scheduleState.next.sector });
  } else {
    els.tessMatchCurrent.textContent = "-";
  }

  const observedHtml = coverage.observed.length
    ? coverage.observed.map((sector) => `<span class="sector-chip observed">S${sector} ✓</span>`).join("")
    : `<span class="sector-chip background">${t("observed_unknown_chip")}</span>`;
  els.tessTimelineObserved.innerHTML = observedHtml;

  const plannedSource = coverage.planned.length
    ? coverage.planned
    : (coverage.observed.length ? [] : scheduleState.schedule.filter((item) => item.phase !== "completed").slice(0, 2));
  const plannedHtml = plannedSource.length
    ? plannedSource.slice(0, 6).map((item) => {
      const cls = coverage.observed.includes(item.sector) ? "candidate" : "planned";
      return `<span class="sector-chip ${cls}">S${item.sector} - ${formatMonthYear(item.start)}</span>`;
    }).join("")
    : `<span class="sector-chip background">${t("planned_unknown_chip")}</span>`;
  els.tessTimelinePlanned.innerHTML = plannedHtml;
  els.tessTimelineNext.textContent = coverage.observed.length
    ? coverage.nextObservationText
    : t("not_computable_missing_history");
  const statusChipClass =
    coverage.statusKey === "green" ? "candidate" :
    coverage.statusKey === "blue" ? "observed" :
    coverage.statusKey === "yellow" ? "planned" :
    coverage.statusKey === "gray" ? "background" :
    "background";
  const statusLabel =
    coverage.statusKey === "green" ? t("status_chip_green") :
    coverage.statusKey === "blue" ? "UPCOMING" :
    coverage.statusKey === "yellow" ? t("status_chip_yellow") :
    coverage.statusKey === "gray" ? t("status_chip_red") :
    t("status_chip_missing");
  const availability = coverage.estimatedDataAvailable ? ` · Data ~ ${formatDate(coverage.estimatedDataAvailable)}` : "";
  els.tessTimelineStatus.innerHTML = `<span class="sector-chip ${statusChipClass}">${statusLabel}</span> ${coverage.statusText}${availability}`;

  renderMapCoverageSummary(coverage);
}

export function renderTess() {
  if (!els.tessCurrentSector) return;
  const {
    now,
    schedule,
    current,
    upcoming,
    completed,
    next
  } = buildTessScheduleState();

  let statusText = t("tess_status_none");
  if (current) {
    const daysLeft = Math.max(0, daysDiff(now, current.endDate));
    statusText = t("tess_status_running", {
      sector: current.sector,
      days: daysLeft,
      date: formatDate(current.end)
    });
  } else if (next) {
    const startsIn = Math.max(0, daysDiff(now, next.startDate));
    statusText = t("tess_status_next", {
      sector: next.sector,
      days: startsIn,
      date: formatDate(next.start)
    });
  }

  els.tessCurrentSector.textContent = current ? `S${current.sector}` : (next ? t("tess_sector_next", { sector: next.sector }) : "-");
  els.tessCurrentWindow.textContent = current ? formatDateRange(current.start, current.end) : (next ? formatDateRange(next.start, next.end) : "-");
  els.tessTotalNumbered.textContent = `1-${tessMission.totalNumberedSectorsPlanned}`;
  els.tessPrimaryCount.textContent = `${tessMission.primaryMissionSectors} (13+13)`;
  els.tessCurrentStatus.textContent = statusText;
  els.tessYear8Info.textContent = tessMission.year8Description;
  els.tessGeometryInfo.textContent = tessMission.geometryDescription;

  const rows = [...completed.slice(-2), ...upcoming.slice(0, 4)];
  if (current) {
    const currentIndex = schedule.findIndex((item) => item.sector === current.sector);
    const before = schedule.slice(Math.max(0, currentIndex - 1), currentIndex);
    const after = schedule.slice(currentIndex + 1, currentIndex + 4);
    const withCurrent = [...before, current, ...after];
    els.tessScheduleRows.innerHTML = withCurrent.map((item) => {
      const statusClass = item.phase === "running" ? "green" : item.phase === "planned" ? "yellow" : "gray";
      return `
        <tr>
          <td><strong>S${item.sector}</strong></td>
          <td>${formatDate(item.start)}</td>
          <td>${formatDate(item.end)}</td>
          <td><span class="pill ${statusClass}">${item.phase === "running" ? t("phase_running") : item.phase === "planned" ? t("phase_planned") : t("phase_completed")}</span></td>
          <td class="wrap-cell">${localizeTessArrangement(item.arrangement)}</td>
        </tr>
      `;
    }).join("");
  } else {
    els.tessScheduleRows.innerHTML = rows.map((item) => {
      const statusClass = item.phase === "planned" ? "yellow" : "gray";
      return `
        <tr>
          <td><strong>S${item.sector}</strong></td>
          <td>${formatDate(item.start)}</td>
          <td>${formatDate(item.end)}</td>
          <td><span class="pill ${statusClass}">${item.phase === "planned" ? t("phase_planned") : t("phase_completed")}</span></td>
          <td class="wrap-cell">${localizeTessArrangement(item.arrangement)}</td>
        </tr>
      `;
    }).join("");
  }

  els.tessUpdatedAt.textContent = t("tess_updated_at", { date: tessMission.sourceCheckedAt });
  const scheduleState = { now, schedule, current, upcoming, completed, next };
  renderTessSectorSummary(scheduleState);
  drawTessSector2d(scheduleState);
  updateTessSector3dData(scheduleState);
}

export function setTessCompareCollapsed(collapsed, store = true) {
  const card = els.tessCompareCard;
  if (!card || !els.tessCompareToggle) return;
  const isCollapsed = Boolean(collapsed);
  card.classList.toggle("is-collapsed", isCollapsed);
  els.tessCompareToggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
  els.tessCompareToggle.title = isCollapsed
    ? t("tess_compare_expand")
    : t("tess_compare_collapse");
  if (store) {
    try {
      localStorage.setItem(TESS_COMPARE_COLLAPSE_KEY, isCollapsed ? "1" : "0");
    } catch (_) {}
  }
  if (!isCollapsed) {
    const tessState = buildTessScheduleState();
    drawTessSector2d(tessState);
    resizeTessSector3d();
    updateTessSector3dData(tessState);
  }
}
