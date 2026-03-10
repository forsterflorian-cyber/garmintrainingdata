import { el, safeHtml, safeText } from "../../lib/formatters.js";

export function renderSyncStatusBadge(sync) {
  const target = el("syncStatusBadge");
  if (!target) {
    return;
  }

  const state = safeText(sync?.syncState, "unknown");
  target.innerHTML = `
    <article class="sync-badge" data-tone="${safeHtml(syncToneForState(state))}">
      <span>Sync</span>
      <strong>${safeHtml(syncLabelForState(state))}</strong>
    </article>
  `;
}

export function syncLabelForState(state) {
  return {
    never_synced: "Never synced",
    fresh: "Fresh",
    stale: "Stale",
    syncing: "Syncing",
    backfilling: "Backfilling",
    success: "Success",
    partial_success: "Partial",
    error: "Error",
    blocked: "Blocked",
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
