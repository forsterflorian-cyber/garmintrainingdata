import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTomorrowImpactPanel({ impact, plannedOptionLabel }) {
  el("forecastLevel").textContent = humanizeOutlook(impact?.outlook);
  el("forecastText").textContent = plannedOptionLabel
    ? `${plannedOptionLabel}: ${safeText(impact?.text)}`
    : safeText(impact?.text, "Select a session to preview tomorrow impact.");
  el("forecastMeta").textContent = impact?.predictedScore === null || impact?.predictedScore === undefined
    ? "No impact yet."
    : `Projected Score ${formatNumber(impact.predictedScore, 2)}`;
  setPanelTone(el("forecastPanel"), impact?.tone || "neutral");
}

function humanizeOutlook(outlook) {
  return {
    "likely quality possible": "Quality Tomorrow",
    "likely moderate": "Moderate Tomorrow",
    "likely easy/recovery": "Easy Tomorrow",
  }[outlook] || safeText(outlook, "Select a session");
}
