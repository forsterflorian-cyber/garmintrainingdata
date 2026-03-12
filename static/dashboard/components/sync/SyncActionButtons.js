import { el } from "../../lib/formatters.js";

export function renderSyncActionButtons(sync, targetId = "syncActionButtons") {
  const target = el(targetId);
  if (!target) {
    return;
  }

  const disabled = !sync?.canStartSync;
  const retryDisabled = disabled || !["error", "blocked", "stale", "never_synced"].includes(sync?.syncState || "");
  const backfillDays = resolveBackfillDays(sync);

  target.innerHTML = `
    <button class="btn btn-secondary sync-action-btn" type="button" data-action="update" ${disabled ? "disabled" : ""}>Update</button>
    <button class="btn btn-secondary sync-action-btn" type="button" data-action="backfill" ${disabled ? "disabled" : ""}>Backfill ${backfillDays}d</button>
    <button class="btn btn-secondary sync-action-btn" type="button" data-action="retry" ${retryDisabled ? "disabled" : ""}>Retry</button>
  `;
}

function resolveBackfillDays(sync) {
  const days = Number(sync?.targetHistoryDays);
  if (Number.isFinite(days) && days > 0) {
    return Math.trunc(days);
  }
  return 180;
}
