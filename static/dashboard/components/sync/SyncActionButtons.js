import { el } from "../../lib/formatters.js";

export function renderSyncActionButtons(sync) {
  const target = el("syncActionButtons");
  if (!target) {
    return;
  }

  const disabled = !sync?.canStartSync;
  const retryDisabled = disabled || !["error", "blocked", "stale", "never_synced"].includes(sync?.syncState || "");

  target.innerHTML = `
    <button class="btn btn-secondary sync-action-btn" type="button" data-action="update" ${disabled ? "disabled" : ""}>Update</button>
    <button class="btn btn-secondary sync-action-btn" type="button" data-action="backfill" ${disabled ? "disabled" : ""}>Backfill</button>
    <button class="btn btn-secondary sync-action-btn" type="button" data-action="retry" ${retryDisabled ? "disabled" : ""}>Retry</button>
  `;
}
