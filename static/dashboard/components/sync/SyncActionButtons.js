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

export function renderPrimarySyncAction(sync, targetId = "headerSyncAction") {
  const target = el(targetId);
  if (!target) {
    return;
  }

  const action = resolvePrimarySyncAction(sync);
  target.innerHTML = `
    <button
      class="btn btn-secondary sync-action-btn sync-action-btn-compact"
      type="button"
      data-action="${action.type}"
      ${action.disabled ? "disabled" : ""}
    >${action.label}</button>
  `;
}

function resolveBackfillDays(sync) {
  const days = Number(sync?.targetHistoryDays);
  if (Number.isFinite(days) && days > 0) {
    return Math.trunc(days);
  }
  return 180;
}

function resolvePrimarySyncAction(sync) {
  const disabled = !sync?.canStartSync;
  const syncState = sync?.syncState || "";

  if (syncState === "never_synced" || sync?.backfillRecommended) {
    return { type: "backfill", label: "Sync", disabled };
  }

  if (["error", "blocked", "stale"].includes(syncState)) {
    return { type: "retry", label: "Sync", disabled };
  }

  return { type: "update", label: "Sync", disabled };
}
