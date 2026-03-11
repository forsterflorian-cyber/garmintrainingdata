import { el, formatDateTime, formatRelativeHours, safeHtml, safeText } from "../../lib/formatters.js";
import { getSyncUiCopy, syncLabelForState, syncReasonLabel } from "./syncStatusCopy.js";

export function renderSyncStatusPanel(sync, targetId = "syncStatusPanel") {
  const target = el(targetId);
  if (!target) {
    return;
  }

  if (!sync || !sync.syncState) {
    target.innerHTML = '<div class="muted-copy">No Sync Data.</div>';
    return;
  }

  const state = safeText(sync.syncState);
  const display = getSyncUiCopy(sync);
  const reason = display.reasonLabel;
  const backfillLine = sync.backfillRecommended
    ? '<div class="sync-row"><span>Backfill</span><strong>Recommended</strong></div>'
    : "";
  const coverageLine = sync.targetHistoryDays
    ? `<div class="sync-row"><span>History Coverage</span><strong>${safeHtml(String(sync.historyCoverageDays || 0))} / ${safeHtml(String(sync.targetHistoryDays))} days</strong></div>`
    : "";
  const cooldownLine = sync.cooldownUntil
    ? `<div class="sync-row"><span>Cooldown</span><strong>${safeHtml(formatDateTime(sync.cooldownUntil))}</strong></div>`
    : "";
  const messageLines = [display.detail, ...display.advisoryLines]
    .filter(Boolean)
    .map((message) => `<p class="sync-message">${safeHtml(message)}</p>`)
    .join("");
  const errorLine = sync.lastErrorMessage && !display.suppressLastError
    ? `<p class="sync-message is-critical">${safeHtml(sync.lastErrorMessage)}</p>`
    : "";
  const debugLine = sync.debug
    ? `<div class="sync-debug">reason=${safeHtml(sync.debug.autoSyncDecisionReason || "-")} lock=${safeHtml(String(sync.debug.lockActive))} cooldown=${safeHtml(String(sync.debug.cooldownActive))} missing=${safeHtml(String(sync.debug.missingDaysCount ?? "-"))}/${safeHtml(String(sync.debug.missingDaysWindowDays ?? "-"))}</div>`
    : "";

  target.innerHTML = `
    <article class="sync-panel" data-tone="${safeHtml(display.tone)}">
      <div class="sync-panel-head">
        <span class="eyebrow">Sync</span>
        <strong>${safeHtml(display.headline || syncLabelForState(state))}</strong>
      </div>
      ${messageLines}
      <div class="sync-row"><span>Last Success</span><strong>${safeHtml(formatRelativeHours(sync.lastSuccessfulSyncAt))}</strong></div>
      <div class="sync-row"><span>Updated</span><strong>${safeHtml(formatDateTime(sync.lastFinishedSyncAt || sync.lastSuccessfulSyncAt))}</strong></div>
      <div class="sync-row"><span>Status</span><strong>${safeHtml(reason)}</strong></div>
      ${sync.missingDaysCount ? `<div class="sync-row"><span>Missing Days</span><strong>${safeHtml(String(sync.missingDaysCount))}${sync.missingDaysWindowDays ? safeHtml(` / ${sync.missingDaysWindowDays}d`) : ""}</strong></div>` : ""}
      ${coverageLine}
      ${backfillLine}
      ${cooldownLine}
      ${errorLine}
      ${debugLine}
    </article>
  `;
}

export { syncReasonLabel };
