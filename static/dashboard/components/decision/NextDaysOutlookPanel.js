import { el, safeHtml, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderNextDaysOutlookPanel(outlook) {
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
      <div class="outlook-copy">
        <span class="outlook-label">${safeHtml(day.label)}</span>
        <strong>${safeHtml(day.recommendation)}</strong>
      </div>
      <span class="outlook-chip" data-tone="${safeHtml(day.tone || "neutral")}">${safeHtml(day.statusChip || day.recoveryStatus || "")}</span>
    </div>
  `).join("");
  meta.textContent = "Updates immediately when you select a different option.";
  setPanelTone(panel, strongestTone(outlook.days));
}

function strongestTone(days) {
  if (days.some((day) => day.tone === "critical")) {
    return "critical";
  }
  if (days.some((day) => day.tone === "warning")) {
    return "warning";
  }
  if (days.some((day) => day.tone === "positive")) {
    return "positive";
  }
  return "neutral";
}
