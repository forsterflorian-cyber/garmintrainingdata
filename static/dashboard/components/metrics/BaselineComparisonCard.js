import { el } from "../../lib/formatters.js";
import { renderMetricDeltaBar } from "./MetricDeltaBar.js";

export function renderBaselineComparisonCard(bars) {
  const target = el("baselineMetricList");
  if (!bars || !bars.length) {
    target.innerHTML = '<div class="muted-copy">No baseline comparison available.</div>';
    return;
  }

  target.innerHTML = bars.map((metric) => renderMetricDeltaBar(metric)).join("");
}
