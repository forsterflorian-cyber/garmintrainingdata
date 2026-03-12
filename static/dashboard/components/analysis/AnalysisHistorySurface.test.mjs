import test from "node:test";
import assert from "node:assert/strict";

import { renderAnalysisHistorySurface } from "./AnalysisHistorySurface.js";

function createFakeElement() {
  return {
    innerHTML: "",
    textContent: "",
    dataset: {},
    querySelectorAll() {
      return [];
    },
  };
}

function withFakeDocument(elements, callback) {
  const previousDocument = global.document;
  global.document = {
    getElementById(id) {
      return elements[id] || null;
    },
  };

  try {
    callback();
  } finally {
    global.document = previousDocument;
  }
}

test("unified history renders inline heat selectors and selected-day activities", () => {
  const elements = {
    historyTable: createFakeElement(),
    activityHeadline: createFakeElement(),
    activitySelectionMeta: createFakeElement(),
    activityDaySummary: createFakeElement(),
    activityList: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderAnalysisHistorySurface({
      date: "2026-03-12",
      history: {
        rows: [
          {
            date: "2026-03-11",
            readiness: 68,
            loadDay: 40,
            ratio7to28: 0.96,
            primaryRecommendation: "Easy Aerobic",
          },
          {
            date: "2026-03-12",
            readiness: 74,
            loadDay: 76,
            ratio7to28: 1.08,
            primaryRecommendation: "Moderate only",
          },
        ],
      },
      decision: {
        primaryRecommendation: "Moderate only",
      },
      detail: {
        activeDate: "2026-03-12",
        sessionType: "moderate",
        activities: [
          {
            name: "Lunch Ride",
            type_key: "cycling",
            start_local: "2026-03-12 12:00",
            duration_min: 52,
            training_load: 71,
            sport_tag: "bike",
            sessionType: "moderate",
          },
        ],
      },
    });
  });

  assert.match(elements.historyTable.innerHTML, /history-heat-cell/);
  assert.match(elements.historyTable.innerHTML, /history-row is-active/);
  assert.doesNotMatch(elements.historyTable.innerHTML, /loadHeatmap/);
  assert.equal(elements.activityHeadline.textContent, "Activities On 2026-03-12");
  assert.equal(elements.activitySelectionMeta.textContent, "Selected in History: 2026-03-12");
  assert.match(elements.activityDaySummary.innerHTML, /1 activity/);
  assert.match(elements.activityList.innerHTML, /Lunch Ride/);
  assert.doesNotMatch(elements.activityList.innerHTML, /undefined/);
});

test("history and activities render safe empty states without leaking duplicate selectors", () => {
  const elements = {
    historyTable: createFakeElement(),
    activityHeadline: createFakeElement(),
    activitySelectionMeta: createFakeElement(),
    activityDaySummary: createFakeElement(),
    activityList: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderAnalysisHistorySurface({
      date: null,
      history: { rows: [] },
      detail: { activities: [] },
      decision: {},
    });
  });

  assert.match(elements.historyTable.innerHTML, /No history yet\./);
  assert.equal(elements.activityHeadline.textContent, "Focus Day Activities");
  assert.equal(elements.activitySelectionMeta.textContent, "History selection will appear here after sync.");
  assert.match(elements.activityList.innerHTML, /No activities recorded for the selected history day\./);
  assert.doesNotMatch(elements.activityDaySummary.innerHTML, /select/i);
});

test("partial activity metadata renders without undefined placeholders", () => {
  const elements = {
    historyTable: createFakeElement(),
    activityHeadline: createFakeElement(),
    activitySelectionMeta: createFakeElement(),
    activityDaySummary: createFakeElement(),
    activityList: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderAnalysisHistorySurface({
      date: "2026-03-13",
      history: {
        rows: [
          {
            date: "2026-03-13",
            readiness: null,
            loadDay: null,
            ratio7to28: null,
            primaryRecommendation: null,
          },
        ],
      },
      decision: {
        primaryRecommendation: "Easy Aerobic",
      },
      detail: {
        activeDate: "2026-03-13",
        activities: [
          {
            type_key: "running",
            date_local: "2026-03-13",
          },
        ],
      },
    });
  });

  assert.match(elements.activityList.innerHTML, /Partial Garmin metadata|running/);
  assert.doesNotMatch(elements.activityList.innerHTML, /undefined|null/);
});
