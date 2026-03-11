import test from "node:test";
import assert from "node:assert/strict";

import { getSyncUiCopy } from "./syncStatusCopy.js";

test("cooldown states render as paused with backfill advisories", () => {
  const display = getSyncUiCopy({
    syncState: "error",
    statusReason: "cooldown_active",
    cooldownUntil: "2099-03-11T12:00:00Z",
    lastErrorMessage: "Sync failed unexpectedly.",
    missingDaysCount: 28,
    missingDaysWindowDays: 180,
    backfillRecommended: true,
  });

  assert.equal(display.headline, "Sync temporarily paused");
  assert.equal(display.reasonLabel, "Retry available after cooldown");
  assert.equal(display.tone, "warning");
  assert.equal(display.suppressLastError, true);
  assert.deepEqual(display.advisoryLines, ["Backfill recommended", "28 missing days detected in 180d"]);
});

test("blocked auth states stay separate from generic failures", () => {
  const display = getSyncUiCopy({
    syncState: "blocked",
    statusReason: "credentials_invalid",
    lastErrorCode: "garmin_invalid_credentials",
  });

  assert.equal(display.headline, "Reconnect Garmin required");
  assert.equal(display.reasonLabel, "Reconnect Garmin required");
  assert.equal(display.tone, "critical");
  assert.equal(display.suppressLastError, true);
});

test("active sync states stay operational", () => {
  const display = getSyncUiCopy({
    syncState: "syncing",
    statusReason: "already_running",
  });

  assert.equal(display.headline, "Sync in progress");
  assert.equal(display.summaryText, "Sync in progress");
  assert.equal(display.tone, "warning");
});

test("unknown errors keep the generic failure copy", () => {
  const display = getSyncUiCopy({
    syncState: "error",
    statusReason: "sync_error",
    lastErrorCode: "sync_unknown_error",
  });

  assert.equal(display.headline, "Sync failed unexpectedly");
  assert.equal(display.reasonLabel, "Unexpected failure");
  assert.equal(display.tone, "critical");
  assert.equal(display.suppressLastError, false);
});

test("never-synced states explain the initial backfill window", () => {
  const display = getSyncUiCopy({
    syncState: "never_synced",
    targetHistoryDays: 180,
  });

  assert.equal(display.headline, "No successful sync yet");
  assert.equal(display.detail, "Run the initial 180-day backfill to build analysis history.");
});
