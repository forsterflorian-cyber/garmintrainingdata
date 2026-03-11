import { el, formatDateTime, formatRelativeHours, safeHtml, safeText } from "../../lib/formatters.js";
import { syncLabelForState, syncToneForState } from "./SyncStatusBadge.js";

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
        <span class="eyebrow">Sync</span>
        <strong>${safeHtml(syncLabelForState(state))}</strong>
      </div>
      <div class="sync-row"><span>Last Success</span><strong>${safeHtml(formatRelativeHours(sync.lastSuccessfulSyncAt))}</strong></div>
      <div class="sync-row"><span>Updated</span><strong>${safeHtml(formatDateTime(sync.lastFinishedSyncAt || sync.lastSuccessfulSyncAt))}</strong></div>
      <div class="sync-row"><span>Reason</span><strong>${safeHtml(reason)}</strong></div>
      ${sync.missingDaysCount ? `<div class="sync-row"><span>Missing Days</span><strong>${safeHtml(String(sync.missingDaysCount))}</strong></div>` : ""}
      ${backfillLine}
      ${cooldownLine}
      ${errorLine}
      ${debugLine}
    </article>
  `;
}

export function syncReasonLabel(reason) {
  return {
    already_running: "Syncing",
    auto_sync_disabled: "Paused",
    blocked: "Blocked",
    completed: "Success",
    credentials_invalid: "Reconnect Garmin",
    credentials_missing: "Reconnect Garmin",
    credentials_updated: "Ready",
    cooldown_active: "Retry Later",
    fresh_no_action: "Fresh",
    gap_detected: "Backfill",
    garmin_invalid_credentials: "Reconnect Garmin",
    garmin_temporary_error: "Retry",
    manual_request: "Update",
    missing_recent_day: "Update",
    never_synced: "Never Synced",
    partial_success: "Partial Success",
    stale_data: "Stale",
    sync_error: "Error",
    sync_configuration_invalid: "Blocked",
    sync_unknown_error: "Error",
  }[reason] || safeText(reason);
}
