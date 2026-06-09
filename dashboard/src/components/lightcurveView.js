import { state } from '../state.js';
import { t, formatNumber, formatMaybe } from '../i18n.js';
import { els, data, isSpcPrepCandidate, colorName, countWhere, DASHBOARD_UI_VERSION } from '../dataLoader.js';
import { matchesCandidate } from './candidateList.js';

export function curveMatchesFilter(candidate, filter = state.curveFilter) {
  if (filter === "all") return true;
  if (filter === "violet") return candidate.isViolet;
  if (filter === "spc-prep") return isSpcPrepCandidate(candidate);
  if (filter === "orange") return candidate.color === "yellow" && !isSpcPrepCandidate(candidate);
  return candidate.color === filter;
}

export function filteredCurves() {
  const term = els.curveSearch ? els.curveSearch.value.trim().toLowerCase() : "";
  return data.lightcurveCandidates.filter((candidate) => {
    const matchesFilter = curveMatchesFilter(candidate, state.curveFilter);
    return matchesFilter && matchesCandidate(candidate, term);
  });
}

export function candidateHasCurveSource(candidate) {
  if (!candidate) return false;
  return Boolean(
    String(candidate.lightcurveImgDeploy || "").trim() ||
    String(candidate.lightcurveImg || "").trim() ||
    String(candidate.lightcurveImgLocal || "").trim() ||
    String(candidate.folder || "").trim()
  );
}

export function curveForCandidate(candidate) {
  if (!candidate) return null;
  return data.lightcurveCandidates.find((item) => item.tic === candidate.tic) ||
    (candidateHasCurveSource(candidate) ? candidate : null);
}

export function curveFilterCount(filter) {
  return countWhere(data.lightcurveCandidates || [], (candidate) => curveMatchesFilter(candidate, filter));
}

export function renderCurveFilterCounts() {
  document.querySelectorAll("[data-curve-filter]").forEach((button) => {
    const filter = button.dataset.curveFilter;
    const baseLabel = t(`curves_filter_${filter.replace("-", "_")}`);
    button.textContent = `${baseLabel} (${formatNumber(curveFilterCount(filter))})`;
  });
}

export function scrollSelectedCurveIntoView(behavior = "smooth") {
  if (!els.curveList) return;
  const active = els.curveList.querySelector(".curve-item.active");
  if (!active) return;
  const targetTop = active.offsetTop - els.curveList.offsetTop - (els.curveList.clientHeight - active.offsetHeight) / 2;
  els.curveList.scrollTo({
    top: Math.max(0, targetTop),
    behavior
  });
}

export function renderCurves(reset = true, syncScroll = false) {
  const curves = filteredCurves();
  const activeCandidate = state.selectedCandidate || state.selected;
  const selectedFallback = curveForCandidate(activeCandidate);
  if (!activeCandidate) {
    state.selectedCurve = null;
  }
  if (reset || !state.selectedCurve || !curves.some((item) => item.tic === state.selectedCurve.tic)) {
    state.selectedCurve = activeCandidate
      ? curves.find((item) => item.tic === activeCandidate.tic) || selectedFallback || null
      : null;
  }
  if (els.curveList) {
    els.curveList.innerHTML = curves.map((candidate) => `
      <button class="curve-item ${state.selectedCurve && state.selectedCurve.tic === candidate.tic ? "active" : ""}" type="button" data-curve-tic="${candidate.tic}">
        <strong>TIC ${candidate.tic}</strong>
        <span>${colorName(candidate)} · ${candidate.hz || t("not_hz")} · SNR ${candidate.snr}</span>
      </button>
    `).join("");
  }
  renderCurveViewer();
  if (syncScroll && els.curveList) {
    window.requestAnimationFrame(() => scrollSelectedCurveIntoView());
  }
}

export function renderCurveViewer() {
  const candidate = state.selectedCurve;
  if (!candidate) {
    els.curveTitle.textContent = "Bitte Kandidaten auswaehlen";
    els.curveMeta.textContent = "";
    els.curveImageWrap.innerHTML = `<div class="notice">Bitte Kandidaten auswaehlen, um die Lichtkurve zu sehen.</div>`;
    return;
  }

  function collectCurveSources(item) {
    const sources = [];
    const bustToken = encodeURIComponent(String(data.generatedAt || DASHBOARD_UI_VERSION || Date.now()));
    const push = (src) => {
      const value = String(src || "").trim();
      if (!value) return;
      const sep = value.includes("?") ? "&" : "?";
      const withBust = `${value}${sep}v=${bustToken}`;
      if (!sources.includes(withBust)) sources.push(withBust);
      if (!sources.includes(value)) sources.push(value);
    };
    push(item.lightcurveImgDeploy);
    push(item.lightcurveImg);
    push(item.lightcurveImgLocal);
    const folder = String(item.folder || "").trim();
    if (folder) {
      push(`${folder}/lichtkurven_png/LICHTKURVE_COMBINED.png`);
      push(`../${folder}/lichtkurven_png/LICHTKURVE_COMBINED.png`);
      push(`../../${folder}/lichtkurven_png/LICHTKURVE_COMBINED.png`);
    }
    return sources;
  }

  function renderMissingCurve(item, triedSources) {
    const triedList = triedSources
      .map((src) => `<li><code>${src}</code></li>`)
      .join("");
    els.curveImageWrap.innerHTML = `
      <div class="notice">
        ${t("curve_load_failed")}<br />
        TIC ${item.tic} · ${item.folder || t("folder_missing")}<br />
        <ul style="margin:8px 0 0 18px; padding:0;">${triedList}</ul>
      </div>
    `;
  }

  els.curveTitle.textContent = `TIC ${candidate.tic}`;
  els.curveMeta.textContent = `${colorName(candidate)} · ${candidate.hz || t("not_hz")} · ${candidate.distance} ly · P ${candidate.period} d`;
  const sources = collectCurveSources(candidate);
  if (!sources.length) {
    renderMissingCurve(candidate, []);
    return;
  }
  els.curveImageWrap.innerHTML = `<div class="notice">${t("loading_curve")}</div>`;
  const tried = [];
  const tryLoad = (index) => {
    if (index >= sources.length) {
      renderMissingCurve(candidate, tried);
      return;
    }
    const src = sources[index];
    tried.push(src);
    const img = document.createElement("img");
    img.alt = `${t("loading_curve").replace(" ...", "")} TIC ${candidate.tic}`;
    img.loading = "lazy";
    let settled = false;
    const settle = (ok) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (!ok) {
        tryLoad(index + 1);
      }
    };
    img.onerror = () => settle(false);
    img.onload = () => settle(true);
    els.curveImageWrap.innerHTML = "";
    els.curveImageWrap.appendChild(img);
    const timer = setTimeout(() => settle(false), 15000);
    try {
      img.src = src;
    } catch (_) {
      tryLoad(index + 1);
    }
  };
  try {
    tryLoad(0);
  } catch (_) {
    renderMissingCurve(candidate, tried);
  }
}
