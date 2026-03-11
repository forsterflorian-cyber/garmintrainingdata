import { el, safeHtml, safeText } from "../../lib/formatters.js";
import { getSyncUiCopy, syncLabelForState } from "./syncStatusCopy.js";

export function renderSyncStatusBadge(sync, targetId = "syncStatusBadge") {
  const target = el(targetId);
  if (!target) {
    return;
  }

  const display = getSyncUiCopy(sync);
  target.innerHTML = `
    <article class="sync-badge" data-tone="${safeHtml(display.tone)}">
      <strong>${safeHtml(syncBadgeText(sync, display))}</strong>
    </article>
  `;
}

function syncBadgeText(sync, display) {
  const state = safeText(sync?.syncState, "unknown");
  if (state === "syncing" || state === "backfilling") {
    return "Sync in progress";
  }
  if (display.headline !== syncLabelForState(state)) {
    return display.headline;
  }
  return `Sync: ${syncLabelForState(state)}`;
}
