import test from "node:test";
import assert from "node:assert/strict";

import { buildForecastContextCopy, compareCompletedSessionToDecision } from "./planDecisionUtils.js";

test("easy session aligns with easy aerobic recommendation", () => {
  const comparison = compareCompletedSessionToDecision("easy", {
    primaryRecommendation: "Easy Aerobic",
  });

  assert.deepEqual(comparison, {
    label: "Aligned with today's recommendation",
    tone: "positive",
  });
});

test("quality session exceeds an easy day recommendation", () => {
  const comparison = compareCompletedSessionToDecision("threshold", {
    primaryRecommendation: "Easy Aerobic",
  });

  assert.deepEqual(comparison, {
    label: "Exceeded today's suggested limit",
    tone: "critical",
  });
});

test("moderate session stays below a threshold recommendation", () => {
  const comparison = compareCompletedSessionToDecision("moderate", {
    primaryRecommendation: "Threshold OK",
  });

  assert.deepEqual(comparison, {
    label: "Below recommended training load",
    tone: "neutral",
  });
});

test("forecast context prefers completed session title and duration", () => {
  const copy = buildForecastContextCopy(
    { title: "Easy Ride", durationMinutes: 29, label: "Easy Ride" },
    { forecastInputMode: "actual" },
  );

  assert.equal(copy, "Based on today's Easy Ride / 29 min");
});

test("aligned comparison can include mode-priority detail", () => {
  const comparison = compareCompletedSessionToDecision("moderate", {
    primaryRecommendation: "Moderate only",
    bestOptions: [{ sportTag: "run" }],
  }, {
    sportTag: "bike",
  });

  assert.equal(comparison.label, "Aligned with today's recommendation");
  assert.equal(comparison.detail, "Run focus had priority today.");
});
