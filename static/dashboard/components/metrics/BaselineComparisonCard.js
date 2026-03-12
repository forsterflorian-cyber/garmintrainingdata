import { el } from "../../lib/formatters.js";
import { renderMetricDeltaBar } from "./MetricDeltaBar.js";

export function renderBaselineComparisonCard(
  bars,
  { targetId = "baselineMetricList", emptyCopy = "No baseline comparison available." } = {},
) {
  const target = el(targetId);
  if (!target) {
    return;
  }
  if (!bars || !bars.length) {
    target.innerHTML = `<div class="muted-copy">${emptyCopy}</div>`;
    return;
  }

  target.innerHTML = bars.map((metric) => renderMetricDeltaBar(metric)).join("");
}
