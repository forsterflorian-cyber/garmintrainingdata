import { el, safeHtml, safeText } from "../../lib/formatters.js";
import { getSyncUiCopy, syncLabelForState } from "./syncStatusCopy.js";

export function renderSyncStatusBadge(sync, targetId = "syncStatusBadge") {
  const target = el(targetId);
  if (!target) {
    return;
  }

  const state = safeText(sync?.syncState, "unknown");
  const display = getSyncUiCopy(sync);
  target.innerHTML = `
    <article class="sync-badge" data-tone="${safeHtml(display.tone)}">
      <span class="sync-badge-label">Sync</span>
      <strong class="sync-badge-value">${safeHtml(syncBadgeValue(sync, display, state))}</strong>
    </article>
  `;
}

function syncBadgeValue(sync, display, state) {
  if (state === "syncing" || state === "backfilling") {
    return "In Progress";
  }
  if (display.headline !== syncLabelForState(state)) {
    return display.headline;
  }
  return syncLabelForState(state);
}
