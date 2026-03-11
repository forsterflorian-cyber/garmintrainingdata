import { safeText } from "../../lib/formatters.js";

const ACTIVE_SYNC_STATES = new Set(["syncing", "backfilling"]);
const RECONNECT_REASONS = new Set([
  "blocked",
  "credentials_invalid",
  "credentials_missing",
  "garmin_invalid_credentials",
  "sync_configuration_invalid",
]);

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

export function syncReasonLabel(reason) {
  return {
    already_running: "Sync in progress",
    auto_sync_disabled: "Auto sync paused",
    blocked: "Reconnect Garmin required",
    completed: "Sync complete",
    credentials_invalid: "Reconnect Garmin required",
    credentials_missing: "Reconnect Garmin required",
    credentials_updated: "Ready",
    cooldown_active: "Retry available after cooldown",
    fresh_no_action: "No action needed",
    gap_detected: "Backfill recommended",
    garmin_invalid_credentials: "Reconnect Garmin required",
    garmin_temporary_error: "Temporary Garmin issue",
    initial_backfill: "Initial backfill recommended",
    manual_request: "Sync requested",
    missing_recent_day: "Recent data missing",
    never_synced: "No successful sync yet",
    partial_success: "Sync partially complete",
    stale_data: "Data refresh recommended",
    sync_error: "Sync needs attention",
    sync_configuration_invalid: "Reconnect Garmin required",
    sync_unknown_error: "Sync failed unexpectedly",
  }[reason] || safeText(reason);
}

export function getSyncUiCopy(sync = {}) {
  const state = safeText(sync?.syncState, "unknown");
  const reason = safeText(sync?.statusReason, "");
  const errorCode = safeText(sync?.lastErrorCode, "");
  const advisoryLines = buildAdvisoryLines(sync);
  const reconnectRequired = isReconnectRequired(sync, reason, errorCode);
  const cooldownActive = isCooldownState(sync, reason);
  const activeSync = ACTIVE_SYNC_STATES.has(state);

  const copy = {
    headline: syncLabelForState(state),
    tone: syncToneForState(state),
    reasonLabel: syncReasonLabel(reason),
    detail: "",
    advisoryLines,
    summaryText: "",
    metaText: "",
    suppressLastError: false,
  };

  if (activeSync) {
    return {
      ...copy,
      headline: "Sync in progress",
      tone: "warning",
      reasonLabel: "Sync in progress",
      summaryText: "Sync in progress",
      metaText: "Sync in progress",
      suppressLastError: true,
    };
  }

  if (reconnectRequired) {
    return {
      ...copy,
      headline: "Reconnect Garmin required",
      tone: "critical",
      reasonLabel: "Reconnect Garmin required",
      detail: "Update Garmin credentials in settings.",
      summaryText: "Reconnect Garmin required",
      metaText: "Reconnect Garmin required",
      suppressLastError: true,
    };
  }

  if (cooldownActive) {
    return {
      ...copy,
      headline: "Sync temporarily paused",
      tone: "warning",
      reasonLabel: "Retry available after cooldown",
      detail: "Retry available after cooldown",
      summaryText: "Sync temporarily paused",
      metaText: "Retry available after cooldown",
      suppressLastError: true,
    };
  }

  if (state === "error" && errorCode === "garmin_temporary_error") {
    return {
      ...copy,
      headline: "Temporary Garmin issue",
      tone: "warning",
      reasonLabel: "Temporary Garmin issue",
      detail: "Retry later.",
      summaryText: "Temporary Garmin issue",
      metaText: "Retry later",
    };
  }

  if (state === "error" && (errorCode === "sync_unknown_error" || !reason || reason === "sync_error")) {
    return {
      ...copy,
      headline: "Sync failed unexpectedly",
      tone: "critical",
      reasonLabel: "Unexpected failure",
      summaryText: "Sync failed unexpectedly",
      metaText: "Sync needs attention",
    };
  }

  if (state === "partial_success") {
    return {
      ...copy,
      headline: "Sync partially complete",
      tone: "warning",
      reasonLabel: "Sync partially complete",
      summaryText: "Sync partially complete",
      metaText: "Sync partially complete",
    };
  }

  if (state === "never_synced") {
    return {
      ...copy,
      headline: "No successful sync yet",
      reasonLabel: "No successful sync yet",
      detail: sync?.targetHistoryDays
        ? `Run the initial ${safeText(sync.targetHistoryDays)}-day backfill to build analysis history.`
        : "",
      summaryText: "No successful sync yet",
      metaText: "Never synced",
    };
  }

  return copy;
}

function buildAdvisoryLines(sync) {
  const advisoryLines = [];
  const missingDaysCount = normalizeMissingDays(sync?.missingDaysCount);
  const windowDays = normalizeMissingDays(sync?.missingDaysWindowDays) || normalizeMissingDays(sync?.targetHistoryDays);

  if (sync?.backfillRecommended) {
    advisoryLines.push("Backfill recommended");
  }
  if (missingDaysCount > 0 && (sync?.backfillRecommended || missingDaysCount >= 7)) {
    advisoryLines.push(windowDays ? `${missingDaysCount} missing days detected in ${windowDays}d` : `${missingDaysCount} missing days detected`);
  }

  return advisoryLines;
}

function isCooldownState(sync, reason) {
  if (reason === "cooldown_active") {
    return true;
  }
  if (sync?.debug?.cooldownActive === true) {
    return true;
  }

  const cooldownUntil = sync?.cooldownUntil;
  if (!cooldownUntil) {
    return false;
  }

  const until = new Date(cooldownUntil);
  return !Number.isNaN(until.getTime()) && until.getTime() > Date.now();
}

function isReconnectRequired(sync, reason, errorCode) {
  if (safeText(sync?.syncState, "") === "blocked") {
    return true;
  }
  return RECONNECT_REASONS.has(reason) || RECONNECT_REASONS.has(errorCode);
}

function normalizeMissingDays(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 0;
  }
  return Math.trunc(parsed);
}
