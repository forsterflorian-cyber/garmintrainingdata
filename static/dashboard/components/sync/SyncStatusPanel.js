import { el, formatDateTime, formatRelativeHours, safeHtml, safeText } from "../../lib/formatters.js";
import { syncLabelForState, syncToneForState } from "./SyncStatusBadge.js";

export function renderSyncStatusPanel(sync) {
  const target = el("syncStatusPanel");
  if (!target) {
    return;
  }

  if (!sync || !sync.syncState) {
    target.innerHTML = '<div class="muted-copy">No sync metadata available.</div>';
    return;
  }

  const state = safeText(sync.syncState);
  const reason = syncReasonLabel(sync.statusReason);
  const backfillLine = sync.backfillRecommended
    ? '<div class="sync-row"><span>Backfill</span><strong>Recommended</strong></div>'
    : "";
  const cooldownLine = sync.cooldownUntil
    ? `<div class="sync-row"><span>Cooldown</span><strong>${safeHtml(formatDateTime(sync.cooldownUntil))}</strong></div>`
    : "";
  const errorLine = sync.lastErrorMessage
    ? `<p class="sync-message is-critical">${safeHtml(sync.lastErrorMessage)}</p>`
    : "";
  const debugLine = sync.debug
    ? `<div class="sync-debug">reason=${safeHtml(sync.debug.autoSyncDecisionReason || "-")} lock=${safeHtml(String(sync.debug.lockActive))} cooldown=${safeHtml(String(sync.debug.cooldownActive))} missing=${safeHtml(String(sync.debug.missingDaysCount ?? "-"))}</div>`
    : "";

  target.innerHTML = `
    <article class="sync-panel" data-tone="${safeHtml(syncToneForState(state))}">
      <div class="sync-panel-head">
        <span class="eyebrow">Auto-sync</span>
        <strong>${safeHtml(syncLabelForState(state))}</strong>
      </div>
      <div class="sync-row"><span>Last success</span><strong>${safeHtml(formatRelativeHours(sync.lastSuccessfulSyncAt))}</strong></div>
      <div class="sync-row"><span>Updated</span><strong>${safeHtml(formatDateTime(sync.lastFinishedSyncAt || sync.lastSuccessfulSyncAt))}</strong></div>
      <div class="sync-row"><span>Reason</span><strong>${safeHtml(reason)}</strong></div>
      ${sync.missingDaysCount ? `<div class="sync-row"><span>Missing days</span><strong>${safeHtml(String(sync.missingDaysCount))}</strong></div>` : ""}
      ${backfillLine}
      ${cooldownLine}
      ${errorLine}
      ${debugLine}
    </article>
  `;
}

function syncReasonLabel(reason) {
  return {
    already_running: "Sync in progress",
    auto_sync_disabled: "Auto-sync disabled",
    blocked: "Sync blocked",
    credentials_invalid: "Update Garmin credentials",
    credentials_missing: "Connect Garmin",
    cooldown_active: "Retry later",
    fresh_no_action: "Up to date",
    gap_detected: "Historical gap detected",
    manual_request: "Manual sync",
    missing_recent_day: "Recent day missing",
    never_synced: "Initial sync pending",
    stale_data: "Data is stale",
  }[reason] || safeText(reason);
}
