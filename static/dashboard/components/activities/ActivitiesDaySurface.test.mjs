import test from "node:test";
import assert from "node:assert/strict";

import { renderActivitiesDaySurface } from "./ActivitiesDaySurface.js";

function createFakeElement() {
  return {
    innerHTML: "",
    textContent: "",
    dataset: {},
    disabled: false,
    value: "",
    onchange: null,
    onclick: null,
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

test("activities dropdown shows newest days first and renders selected-day content", () => {
  const elements = {
    activitiesDaySelect: createFakeElement(),
    activitiesPrevDayBtn: createFakeElement(),
    activitiesNextDayBtn: createFakeElement(),
    activitiesSelectionMeta: createFakeElement(),
    activitiesActualHeadline: createFakeElement(),
    activitiesActualSummary: createFakeElement(),
    activitiesActualList: createFakeElement(),
    activitiesRecommendationHeadline: createFakeElement(),
    activitiesRecommendationSummary: createFakeElement(),
    activitiesRecommendationWhy: createFakeElement(),
    activitiesRecommendationOptions: createFakeElement(),
    activitiesBaselineHeadline: createFakeElement(),
    activitiesBaselineReference: createFakeElement(),
    activitiesBaselineMetricList: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderActivitiesDaySurface(
      {
        date: "2026-03-09",
        decision: {
          primaryRecommendation: "Moderate only",
          loadTolerance: "Manageable",
          summaryText: "Keep the day controlled.",
          why: ["Recovery is stable.", "Load is near target."],
          bestOptions: [
            { label: "Steady run", details: "45 min at controlled effort." },
          ],
        },
        detail: {
          activeDate: "2026-03-09",
          sessionType: "moderate",
          activities: [
            {
              name: "Lunch Ride",
              type_key: "cycling",
              start_local: "2026-03-09 12:00",
              duration_min: 52,
              training_load: 71,
              sport_tag: "bike",
              sessionType: "moderate",
            },
          ],
        },
        reference: {
          baselineDays: 28,
          baselineSource: "rolling",
          baselineSampleDays: 12,
        },
        baselineBars: [
          {
            label: "HRV",
            deltaPct: 4.2,
            progress: 62,
            value: 58,
            baseline: 55,
            tone: "positive",
          },
        ],
      },
      {
        availableDays: [
          { date: "2026-03-08" },
          { date: "2026-03-09" },
          { date: "2026-03-10" },
        ],
        selectedDate: "2026-03-09",
        todayDate: "2026-03-10",
      },
    );
  });

  const optionMarkup = elements.activitiesDaySelect.innerHTML;
  assert(optionMarkup.indexOf('value="2026-03-10"') < optionMarkup.indexOf('value="2026-03-09"'));
  assert(optionMarkup.indexOf('value="2026-03-09"') < optionMarkup.indexOf('value="2026-03-08"'));
  assert.match(optionMarkup, />Today</);
  assert.match(optionMarkup, />Yesterday</);
  assert.equal(elements.activitiesDaySelect.value, "2026-03-09");
  assert.equal(elements.activitiesPrevDayBtn.disabled, false);
  assert.equal(elements.activitiesNextDayBtn.disabled, false);
  assert.equal(elements.activitiesActualHeadline.textContent, "Activities On 2026-03-09");
  assert.equal(elements.activitiesRecommendationHeadline.textContent, "Recommendation For 2026-03-09");
  assert.equal(elements.activitiesBaselineHeadline.textContent, "2026-03-09 Vs Baseline");
  assert.match(elements.activitiesActualList.innerHTML, /Lunch Ride/);
  assert.match(elements.activitiesRecommendationSummary.innerHTML, /Moderate only/);
  assert.match(elements.activitiesRecommendationWhy.innerHTML, /Recovery is stable/);
  assert.match(elements.activitiesRecommendationOptions.innerHTML, /Steady run/);
  assert.match(elements.activitiesBaselineMetricList.innerHTML, /HRV/);
  assert.doesNotMatch(elements.activitiesActualList.innerHTML, /undefined|null/);
});

test("activities dropdown order stays stable across selection changes", () => {
  const elements = {
    activitiesDaySelect: createFakeElement(),
    activitiesPrevDayBtn: createFakeElement(),
    activitiesNextDayBtn: createFakeElement(),
    activitiesSelectionMeta: createFakeElement(),
    activitiesActualHeadline: createFakeElement(),
    activitiesActualSummary: createFakeElement(),
    activitiesActualList: createFakeElement(),
    activitiesRecommendationHeadline: createFakeElement(),
    activitiesRecommendationSummary: createFakeElement(),
    activitiesRecommendationWhy: createFakeElement(),
    activitiesRecommendationOptions: createFakeElement(),
    activitiesBaselineHeadline: createFakeElement(),
    activitiesBaselineReference: createFakeElement(),
    activitiesBaselineMetricList: createFakeElement(),
  };

  const availableDays = [
    { date: "2026-03-08" },
    { date: "2026-03-09" },
    { date: "2026-03-10" },
  ];

  withFakeDocument(elements, () => {
    renderActivitiesDaySurface({ date: "2026-03-10", detail: {}, decision: {}, baselineBars: [] }, {
      availableDays,
      selectedDate: "2026-03-10",
      todayDate: "2026-03-10",
    });
    const before = elements.activitiesDaySelect.innerHTML;

    renderActivitiesDaySurface({ date: "2026-03-08", detail: {}, decision: {}, baselineBars: [] }, {
      availableDays,
      selectedDate: "2026-03-08",
      todayDate: "2026-03-10",
    });

    assert.equal(elements.activitiesDaySelect.innerHTML, before);
    assert.equal(elements.activitiesDaySelect.value, "2026-03-08");
  });
});

test("activities prev and next buttons move within the available day list", () => {
  const elements = {
    activitiesDaySelect: createFakeElement(),
    activitiesPrevDayBtn: createFakeElement(),
    activitiesNextDayBtn: createFakeElement(),
    activitiesSelectionMeta: createFakeElement(),
    activitiesActualHeadline: createFakeElement(),
    activitiesActualSummary: createFakeElement(),
    activitiesActualList: createFakeElement(),
    activitiesRecommendationHeadline: createFakeElement(),
    activitiesRecommendationSummary: createFakeElement(),
    activitiesRecommendationWhy: createFakeElement(),
    activitiesRecommendationOptions: createFakeElement(),
    activitiesBaselineHeadline: createFakeElement(),
    activitiesBaselineReference: createFakeElement(),
    activitiesBaselineMetricList: createFakeElement(),
  };

  const selectedDates = [];

  withFakeDocument(elements, () => {
    renderActivitiesDaySurface({ date: "2026-03-09", detail: {}, decision: {}, baselineBars: [] }, {
      availableDays: [
        { date: "2026-03-08" },
        { date: "2026-03-09" },
        { date: "2026-03-10" },
      ],
      selectedDate: "2026-03-09",
      todayDate: "2026-03-10",
      onSelectDay(date) {
        selectedDates.push(date);
      },
    });

    elements.activitiesPrevDayBtn.onclick();
    elements.activitiesNextDayBtn.onclick();
  });

  assert.deepEqual(selectedDates, ["2026-03-08", "2026-03-10"]);
});

test("activities surface renders safe empty states for sparse history", () => {
  const elements = {
    activitiesDaySelect: createFakeElement(),
    activitiesPrevDayBtn: createFakeElement(),
    activitiesNextDayBtn: createFakeElement(),
    activitiesSelectionMeta: createFakeElement(),
    activitiesActualHeadline: createFakeElement(),
    activitiesActualSummary: createFakeElement(),
    activitiesActualList: createFakeElement(),
    activitiesRecommendationHeadline: createFakeElement(),
    activitiesRecommendationSummary: createFakeElement(),
    activitiesRecommendationWhy: createFakeElement(),
    activitiesRecommendationOptions: createFakeElement(),
    activitiesBaselineHeadline: createFakeElement(),
    activitiesBaselineReference: createFakeElement(),
    activitiesBaselineMetricList: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderActivitiesDaySurface(
      {
        date: null,
        detail: { activities: [null] },
        decision: {},
        reference: {},
        baselineBars: [],
      },
      {
        availableDays: [],
        selectedDate: null,
      },
    );
  });

  assert.equal(elements.activitiesDaySelect.disabled, true);
  assert.equal(elements.activitiesPrevDayBtn.disabled, true);
  assert.equal(elements.activitiesNextDayBtn.disabled, true);
  assert.equal(elements.activitiesSelectionMeta.textContent, "No synced history is available yet.");
  assert.match(elements.activitiesActualList.innerHTML, /No synced history is available yet\./);
  assert.match(elements.activitiesRecommendationSummary.innerHTML, /No recommendation data is available for the selected day\./);
  assert.match(elements.activitiesBaselineMetricList.innerHTML, /No baseline comparison available for the selected day\./);
  assert.doesNotMatch(elements.activitiesRecommendationWhy.innerHTML, /undefined|null/);
});
