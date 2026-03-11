import { el, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTomorrowImpactPanel({
  impact,
  plannedOptionLabel,
  forecastInputMode = "preview",
  sourceContext = null,
}) {
  el("forecastLevel").textContent = safeText(impact?.headline, "Choose today's session");
  el("forecastContext").textContent = safeText(
    sourceContext,
    forecastInputMode === "actual"
      ? "Based on today's completed session."
      : "Based on today's preview.",
  );
  el("forecastText").textContent = safeText(impact?.text, "Select a session to update the best fit for tomorrow.");
  el("forecastMeta").textContent = safeText(
    impact?.windowLabel,
    plannedOptionLabel
      ? "Tomorrow's training window updates with today's choice."
      : "Tomorrow's training window updates after you set today's session.",
  );
  setPanelTone(el("forecastPanel"), impact?.tone || "neutral");
}
