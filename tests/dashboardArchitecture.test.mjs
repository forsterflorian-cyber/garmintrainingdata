import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(fileURLToPath(new URL("..", import.meta.url)));

async function readTemplate(relativePath) {
  return fs.readFile(path.join(REPO_ROOT, relativePath), "utf8");
}

test("analysis view is today-only and restores the today baseline comparison", async () => {
  const analysisTemplate = await readTemplate("templates/_analysis_view.html");

  assert.match(analysisTemplate, /Why This Recommendation/);
  assert.match(analysisTemplate, /Baseline Comparison/);
  assert.match(analysisTemplate, /id="analysisBaselineMetricList"/);
  assert.match(analysisTemplate, /id="baselineReferenceCopy"/);
  assert.doesNotMatch(analysisTemplate, /historyTable/);
  assert.doesNotMatch(analysisTemplate, /activitiesDaySelect/);
  assert.doesNotMatch(analysisTemplate, /data-panel=/);
});

test("dashboard shell exposes the training focus helper and dashboard loading overlay", async () => {
  const dashboardTemplate = await readTemplate("templates/dashboard.html");
  const authTemplate = await readTemplate("templates/_auth_view.html");

  assert.match(dashboardTemplate, /Training Focus/);
  assert.match(dashboardTemplate, /id="modeHelpText"/);
  assert.match(dashboardTemplate, /Hybrid = balanced endurance \+ strength/);
  assert.match(dashboardTemplate, /id="dashboardLoadingOverlay"/);
  assert.match(dashboardTemplate, /Updating dashboard/);
  assert.match(authTemplate, /Setup incomplete\./);
  assert.match(authTemplate, /missing_public_config/);
  assert.match(authTemplate, /auth_disabled/);
});

test("trends and activities views expose the expected focused surfaces", async () => {
  const trendsTemplate = await readTemplate("templates/_trends_view.html");
  const activitiesTemplate = await readTemplate("templates/_activities_view.html");
  const syncTemplate = await readTemplate("templates/_sync_view.html");

  assert.match(trendsTemplate, /id="readinessChart"/);
  assert.match(trendsTemplate, /id="loadChart"/);
  assert.match(trendsTemplate, /currently selected analysis range/);
  assert.match(activitiesTemplate, /id="activitiesDaySelect"/);
  assert.match(activitiesTemplate, /id="activitiesPrevDayBtn"/);
  assert.match(activitiesTemplate, /id="activitiesNextDayBtn"/);
  assert.match(activitiesTemplate, /id="activitiesActualList"/);
  assert.match(activitiesTemplate, /id="activitiesBaselineMetricList"/);
  assert.match(activitiesTemplate, /Choose a day from the current range/);
  assert.match(syncTemplate, /First sync backfills history/);
});
