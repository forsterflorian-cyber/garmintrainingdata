import { el, formatNumber } from "../../lib/formatters.js";

const READINESS_EMPTY_STATE = "Not enough readiness history for the readiness chart.";

export function renderReadinessTrendCard(series, activeDate) {
  drawLineChart("readinessChart", series || [], [{ key: "value", color: "#69e0b5" }], activeDate);
}

function drawLineChart(svgId, series, lines, activeDate) {
  const svg = el(svgId);
  if (!svg) {
    return;
  }
  if (!series.length) {
    svg.innerHTML = emptyStateMarkup();
    svg.dataset.empty = "true";
    return;
  }

  const width = 920;
  const height = 320;
  const left = 54;
  const right = 26;
  const top = 26;
  const bottom = 44;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const values = [];

  lines.forEach((spec) => {
    series.forEach((item) => {
      if (Number.isFinite(item[spec.key])) values.push(Number(item[spec.key]));
    });
  });

  if (!values.length) {
    svg.innerHTML = emptyStateMarkup();
    svg.dataset.empty = "true";
    return;
  }

  const minY = Math.min(...values, 0);
  const maxY = Math.max(...values, 1);
  const xStep = series.length > 1 ? plotWidth / (series.length - 1) : 0;

  let markup = "";
  for (let grid = 0; grid <= 4; grid += 1) {
    const y = top + (grid / 4) * plotHeight;
    const value = maxY - ((maxY - minY) * grid) / 4;
    markup += `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="rgba(173,212,202,0.08)" />`;
    markup += `<text x="${left - 12}" y="${y + 4}" text-anchor="end" font-size="11" fill="rgba(159,176,170,0.78)">${formatNumber(value, 0)}</text>`;
  }

  lines.forEach((spec) => {
    const points = series
      .map((item, index) => {
        const value = Number(item[spec.key]);
        if (!Number.isFinite(value)) return null;
        const x = left + index * xStep;
        const y = top + ((maxY - value) / Math.max(1, maxY - minY)) * plotHeight;
        return { x, y, value, date: item.date };
      })
      .filter(Boolean);

    if (!points.length) return;
    const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
    markup += `<path d="${path}" fill="none" stroke="${spec.color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />`;
    points.forEach((point) => {
      const isActive = point.date === activeDate;
      markup += `<circle cx="${point.x}" cy="${point.y}" r="${isActive ? 5.5 : 3.5}" fill="${isActive ? "#f3f0df" : spec.color}" />`;
    });
  });

  series.forEach((item, index) => {
    const x = left + index * xStep;
    const fill = item.date === activeDate ? "#f3f0df" : "rgba(159,176,170,0.8)";
    markup += `<text x="${x}" y="${height - 12}" text-anchor="middle" font-size="10" fill="${fill}">${item.date.slice(5)}</text>`;
  });

  svg.innerHTML = markup;
  svg.dataset.empty = "false";
}

function emptyStateMarkup() {
  return `
    <rect x="0" y="0" width="920" height="320" fill="rgba(4,16,22,0.72)"></rect>
    <text x="460" y="160" text-anchor="middle" font-size="16" fill="rgba(159,176,170,0.84)">${READINESS_EMPTY_STATE}</text>
  `;
}
