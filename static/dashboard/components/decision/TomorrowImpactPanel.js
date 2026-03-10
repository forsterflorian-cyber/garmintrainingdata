import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTomorrowImpactPanel({ impact, plannedOptionLabel }) {
  el("forecastLevel").textContent = safeText(impact?.outlook, "select a session");
  el("forecastText").textContent = plannedOptionLabel
    ? `${plannedOptionLabel}: ${safeText(impact?.text)}`
    : safeText(impact?.text, "Select a planned session to project tomorrow.");
  el("forecastMeta").textContent = impact?.predictedScore === null || impact?.predictedScore === undefined
    ? "No projection yet."
    : `Predicted tomorrow score ${formatNumber(impact.predictedScore, 2)}`;
  setPanelTone(el("forecastPanel"), impact?.tone || "neutral");
}
