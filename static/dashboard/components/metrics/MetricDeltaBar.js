import { formatNumber, formatSigned, safeHtml } from "../../lib/formatters.js";

export function renderMetricDeltaBar(metric) {
  const delta = metric.deltaPct === null || metric.deltaPct === undefined
    ? "No baseline"
    : formatSigned(metric.deltaPct, 1, "%");
  const baseline = metric.baseline === null || metric.baseline === undefined
    ? "-"
    : formatNumber(metric.baseline, 1);

  return `
    <article class="metric-delta-bar" data-tone="${safeHtml(metric.tone || "neutral")}">
      <div class="metric-delta-head">
        <span>${safeHtml(metric.label)}</span>
        <strong>${safeHtml(delta)}</strong>
      </div>
      <div class="metric-track">
        <div class="metric-fill" style="width:${Math.max(8, metric.progress || 0)}%"></div>
      </div>
      <div class="metric-delta-meta">
        <span>Current ${formatNumber(metric.value, 1)}</span>
        <span>Baseline ${baseline}</span>
      </div>
    </article>
  `;
}
