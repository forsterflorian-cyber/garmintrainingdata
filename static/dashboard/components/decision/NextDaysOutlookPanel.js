import { el, safeHtml, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderNextDaysOutlookPanel(outlook, { forecastInputMode = "preview", sourceContext = null } = {}) {
  const title = el("nextDaysOutlookTitle");
  const body = el("nextDaysOutlookBody");
  const meta = el("nextDaysOutlookMeta");
  const panel = el("nextDaysOutlookPanel");

  if (!outlook?.available || !outlook.days?.length) {
    title.textContent = "Outlook Unavailable";
    body.innerHTML = '<div class="muted-copy">Not enough data to project the next few days.</div>';
    meta.textContent = safeText(outlook?.reason, "Select a session to preview the next few days.");
    setPanelTone(panel, "neutral");
    return;
  }

  title.textContent = "Likely Flow";
  body.innerHTML = outlook.days.map((day) => `
    <div class="outlook-row" data-tone="${safeHtml(day.tone || "neutral")}">
      <span class="outlook-day">${safeHtml(day.label)}</span>
      <div class="outlook-copy">
        <strong>${safeHtml(day.recommendation)}</strong>
      </div>
      ${day.statusChip || day.recoveryStatus
        ? `<span class="outlook-chip" data-tone="${safeHtml(day.tone || "neutral")}">${safeHtml(day.statusChip || defaultStatusCopy(day))}</span>`
        : ""}
    </div>
  `).join("");
  meta.textContent = safeText(
    sourceContext,
    forecastInputMode === "actual"
      ? "Forecast follows today's completed session."
      : "Preview updates the next few days.",
  );
  setPanelTone(panel, "neutral");
}

function defaultStatusCopy(day = {}) {
  if (day.recoveryStatus === "Poor") {
    return "Fatigued";
  }
  if (day.recoveryStatus === "Borderline") {
    return "Borderline";
  }
  if (day.recoveryStatus === "Stable" || day.recoveryStatus === "Good") {
    return "Stable";
  }
  return "Low capacity";
}
