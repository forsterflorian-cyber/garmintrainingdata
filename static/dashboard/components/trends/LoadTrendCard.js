import { el, formatNumber } from "../../lib/formatters.js";

const LOAD_CHANNEL_EMPTY_STATE = "Not enough load history for the load channel chart.";

export function renderLoadTrendCard(series, activeDate, momentum = null) {
  renderLoadMomentum(momentum);

  const svg = el("loadChart");
  if (!svg) {
    return;
  }

  const chart = buildLoadChannelMarkup(series || [], activeDate);
  svg.innerHTML = chart.markup;
  svg.dataset.empty = chart.empty ? "true" : "false";
}

export function buildLoadMomentumDisplay(momentum) {
  const value = safeNumber(momentum?.value);
  if (value === null) {
    return {
      valueText: "No data",
      labelText: "Need a complete previous 7d window.",
      tone: "neutral",
    };
  }

  const label = typeof momentum?.label === "string" && momentum.label.trim()
    ? momentum.label.trim()
    : loadMomentumLabel(value);

  return {
    valueText: `${value > 0 ? "+" : ""}${formatNumber(value * 100, 1)}%`,
    labelText: label,
    tone: label.toLowerCase(),
  };
}

export function buildLoadChannelMarkup(series, activeDate) {
  const width = 920;
  const height = 320;
  const left = 54;
  const right = 26;
  const top = 26;
  const bottom = 44;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const normalizedSeries = Array.isArray(series) ? series : [];
  const values = [];

  normalizedSeries.forEach((item) => {
    ["dailyLoad", "load7d", "load28d"].forEach((key) => {
      const value = safeNumber(item?.[key]);
      if (value !== null) {
        values.push(value);
      }
    });
  });

  if (!normalizedSeries.length || !values.length) {
    return {
      empty: true,
      markup: emptyStateMarkup(width, height),
    };
  }

  const maxY = Math.max(...values, 1);
  const xStep = normalizedSeries.length > 1 ? plotWidth / (normalizedSeries.length - 1) : 0;
  const barWidth = Math.max(8, Math.min(20, (plotWidth / Math.max(normalizedSeries.length, 1)) * 0.5));

  let markup = "";
  for (let grid = 0; grid <= 4; grid += 1) {
    const y = top + (grid / 4) * plotHeight;
    const value = maxY - (maxY * grid) / 4;
    markup += `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="rgba(173,212,202,0.08)" />`;
    markup += `<text x="${left - 12}" y="${y + 4}" text-anchor="end" font-size="11" fill="rgba(159,176,170,0.78)">${formatNumber(value, 0)}</text>`;
  }

  normalizedSeries.forEach((item, index) => {
    const x = pointX(index, normalizedSeries.length, left, plotWidth, xStep);
    const dailyLoad = safeNumber(item?.dailyLoad);
    if (dailyLoad === null) {
      return;
    }
    const y = top + ((maxY - dailyLoad) / maxY) * plotHeight;
    const heightValue = Math.max(0, top + plotHeight - y);
    const fill = item.date === activeDate ? "rgba(255, 184, 92, 0.96)" : "rgba(245, 180, 87, 0.72)";
    markup += `<rect x="${x - barWidth / 2}" y="${y}" width="${barWidth}" height="${heightValue}" rx="5" fill="${fill}" />`;
  });

  [
    { key: "load28d", color: "rgba(242,244,238,0.72)", strokeWidth: 2.5 },
    { key: "load7d", color: "#69e0b5", strokeWidth: 3.2 },
  ].forEach((spec) => {
    const points = normalizedSeries.map((item, index) => {
      const value = safeNumber(item?.[spec.key]);
      if (value === null) {
        return null;
      }
      const x = pointX(index, normalizedSeries.length, left, plotWidth, xStep);
      const y = top + ((maxY - value) / maxY) * plotHeight;
      return { x, y, date: item.date };
    });

    const path = buildLinePath(points);
    if (!path) {
      return;
    }

    markup += `<path d="${path}" fill="none" stroke="${spec.color}" stroke-width="${spec.strokeWidth}" stroke-linecap="round" stroke-linejoin="round" />`;
    points.forEach((point) => {
      if (!point) {
        return;
      }
      const isActive = point.date === activeDate;
      markup += `<circle cx="${point.x}" cy="${point.y}" r="${isActive ? 5.2 : 3.2}" fill="${isActive ? "#f3f0df" : spec.color}" />`;
    });
  });

  const labelStep = Math.max(1, Math.ceil(normalizedSeries.length / 8));
  normalizedSeries.forEach((item, index) => {
    const shouldRender = index % labelStep === 0 || index === normalizedSeries.length - 1 || item.date === activeDate;
    if (!shouldRender) {
      return;
    }
    const x = pointX(index, normalizedSeries.length, left, plotWidth, xStep);
    const fill = item.date === activeDate ? "#f3f0df" : "rgba(159,176,170,0.8)";
    const label = typeof item?.date === "string" ? item.date.slice(5) : "--";
    markup += `<text x="${x}" y="${height - 12}" text-anchor="middle" font-size="10" fill="${fill}">${label}</text>`;
  });

  return { empty: false, markup };
}

function renderLoadMomentum(momentum) {
  const card = el("loadMomentumCard");
  if (!card) {
    return;
  }

  const display = buildLoadMomentumDisplay(momentum);
  card.dataset.tone = display.tone;

  const valueTarget = el("loadMomentumValue");
  if (valueTarget) {
    valueTarget.textContent = display.valueText;
  }

  const labelTarget = el("loadMomentumLabel");
  if (labelTarget) {
    labelTarget.textContent = display.labelText;
  }
}

function loadMomentumLabel(value) {
  if (value > 0.10) {
    return "Rising";
  }
  if (value < -0.10) {
    return "Falling";
  }
  return "Stable";
}

function emptyStateMarkup(width, height) {
  return `
    <rect x="0" y="0" width="${width}" height="${height}" fill="rgba(4,16,22,0.72)"></rect>
    <text x="${width / 2}" y="${height / 2}" text-anchor="middle" font-size="16" fill="rgba(159,176,170,0.84)">${LOAD_CHANNEL_EMPTY_STATE}</text>
  `;
}

function pointX(index, totalPoints, left, plotWidth, xStep) {
  if (totalPoints <= 1) {
    return left + plotWidth / 2;
  }
  return left + index * xStep;
}

function buildLinePath(points) {
  let path = "";
  let segmentOpen = false;

  points.forEach((point) => {
    if (!point) {
      segmentOpen = false;
      return;
    }

    path += `${segmentOpen ? " L" : " M"} ${point.x} ${point.y}`;
    segmentOpen = true;
  });

  return path.trim();
}

function safeNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}
