import { el, safeHtml, safeText } from "../../lib/formatters.js";

export function renderSyncStatusBadge(sync) {
  const target = el("syncStatusBadge");
  if (!target) {
    return;
  }

  const state = safeText(sync?.syncState, "unknown");
  target.innerHTML = `
    <article class="sync-badge" data-tone="${safeHtml(syncToneForState(state))}">
      <strong>${safeHtml(syncBadgeText(state))}</strong>
    </article>
  `;
}

export function syncLabelForState(state) {
  return {
    never_synced: "Never Synced",
    fresh: "Fresh",
    stale: "Stale",
    syncing: "Syncing",
    backfilling: "Backfilling",
    success: "Success",
    partial_success: "Partial Success",
    error: "Error",
    blocked: "Blocked",
    unknown: "Unknown",
  }[state] || state;
}

export function syncToneForState(state) {
  if (state === "fresh" || state === "success") {
    return "positive";
  }
  if (state === "syncing" || state === "backfilling" || state === "stale" || state === "partial_success") {
    return "warning";
  }
  if (state === "blocked" || state === "error") {
    return "critical";
  }
  return "neutral";
}

function syncBadgeText(state) {
  if (state === "syncing") {
    return "Syncing...";
  }
  if (state === "backfilling") {
    return "Backfilling...";
  }
  if (state === "error") {
    return "Sync Error";
  }
  return `Sync: ${syncLabelForState(state)}`;
}
