import { state, colors, mapZoom } from '../state.js';
import { t, formatNumber } from '../i18n.js';
import { els, data, selectedMapFocus, candidateMapColor, points2d } from '../dataLoader.js';
import { filteredCandidates } from './candidateList.js';

export function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * scale));
  canvas.height = Math.max(1, Math.floor(rect.height * scale));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  return { ctx, width: rect.width, height: rect.height };
}

export function draw2dMap() {
  const { ctx, width, height } = setupCanvas(els.mapCanvas);
  const candidates = filteredCandidates().filter((candidate) => candidate.color !== "gray");
  const focus = selectedMapFocus(candidates);
  const focusBaseX = width / 2;
  const focusBaseY = height / 2;
  document.getElementById("visibleCount").textContent = formatNumber(candidates.length);
  points2d.length = 0;
  ctx.clearRect(0, 0, width, height);
  const gradient = ctx.createRadialGradient(width * 0.5, height * 0.5, 20, width * 0.5, height * 0.5, width * 0.7);
  gradient.addColorStop(0, "#18282b");
  gradient.addColorStop(1, "#0c1416");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let r = 70 * mapZoom; r < Math.min(width, height) * 0.9; r += 70 * mapZoom) {
    ctx.beginPath();
    ctx.arc(focusBaseX, focusBaseY, r, 0, Math.PI * 2);
    ctx.stroke();
  }

  const centerX = width / 2;
  const centerY = height / 2;
  const axisTop = 42;
  const axisBottom = height - 42;
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.fillStyle = "rgba(255,255,255,0.54)";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 7]);
  ctx.beginPath();
  ctx.moveTo(centerX, axisTop);
  ctx.lineTo(centerX, axisBottom);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.font = "700 11px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("N", centerX, axisTop - 12);
  ctx.fillText("S", centerX, axisBottom + 20);
  ctx.restore();

  candidates.forEach((candidate) => {
    const x = focus
      ? focusBaseX + (candidate.map.x - focus.map.x) * width * 0.42 * mapZoom
      : width / 2 + candidate.map.x * width * 0.42 * mapZoom;
    const y = focus
      ? focusBaseY + (candidate.map.y - focus.map.y) * height * 0.42 * mapZoom
      : height / 2 + candidate.map.y * height * 0.42 * mapZoom;
    if (x < -30 || x > width + 30 || y < -30 || y > height + 30) return;
    const size = Math.max(2, Math.min(10, (candidate.snr || 1) * 0.36 + 1.4));
    ctx.beginPath();
    ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fillStyle = candidateMapColor(candidate);
    ctx.fill();
    if (state.selected && state.selected.tic === candidate.tic) {
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    points2d.push({ x, y, radius: size + 8, candidate });
  });

  const sunX = focus ? focusBaseX - focus.map.x * width * 0.42 * mapZoom : centerX;
  const sunY = focus ? focusBaseY - focus.map.y * height * 0.42 * mapZoom : centerY;
  ctx.beginPath();
  ctx.arc(sunX, sunY, 11, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(244, 201, 109, 0.16)";
  ctx.fill();
  ctx.beginPath();
  ctx.arc(sunX, sunY, 4.5, 0, Math.PI * 2);
  ctx.fillStyle = colors.sun;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(sunX, sunY, 7, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255, 242, 212, 0.78)";
  ctx.lineWidth = 1.2;
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.72)";
  ctx.font = "700 12px Inter, system-ui, sans-serif";
  ctx.fillText(t("chart_legend_map"), 14, 22);
}
