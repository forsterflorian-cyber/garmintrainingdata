import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTomorrowImpactPanel({
  impact,
  plannedOptionLabel,
  forecastInputMode = "preview",
  sourceContext = null,
}) {
  el("forecastLevel").textContent = safeText(impact?.headline, "Select a session");
  el("forecastContext").textContent = safeText(
    sourceContext,
    plannedOptionLabel
      ? `Previewing ${plannedOptionLabel}`
      : forecastInputMode === "actual"
        ? "Based on today's completed session"
        : "Preview a session to update tomorrow impact",
  );
  el("forecastText").textContent = safeText(impact?.text, "Select a session to preview tomorrow impact.");
  el("forecastMeta").textContent = impact?.predictedScore === null || impact?.predictedScore === undefined
    ? "No impact projected yet."
    : `Projected recovery score ${formatNumber(impact.predictedScore, 2)}.`;
  setPanelTone(el("forecastPanel"), impact?.tone || "neutral");
}
