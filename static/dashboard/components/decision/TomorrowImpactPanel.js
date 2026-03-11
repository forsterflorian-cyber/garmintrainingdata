import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTomorrowImpactPanel({ impact, plannedOptionLabel, forecastInputMode = "preview" }) {
  el("forecastLevel").textContent = safeText(impact?.headline, "Select a session");
  el("forecastText").textContent = plannedOptionLabel
    ? `${plannedOptionLabel}: ${safeText(impact?.text)}`
    : safeText(impact?.text, "Select a session to preview tomorrow impact.");
  const scoreCopy = impact?.predictedScore === null || impact?.predictedScore === undefined
    ? "No impact yet."
    : `Projected score ${formatNumber(impact.predictedScore, 2)}.`;
  const modeCopy = forecastInputMode === "actual"
    ? "Using the completed session."
    : "Using the selected preview.";
  el("forecastMeta").textContent = `${scoreCopy} ${modeCopy}`;
  setPanelTone(el("forecastPanel"), impact?.tone || "neutral");
}
