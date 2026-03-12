import test from "node:test";
import assert from "node:assert/strict";

import { buildLoadChannelMarkup, renderLoadTrendCard } from "./LoadTrendCard.js";

function createFakeElement() {
  return {
    innerHTML: "",
    textContent: "",
    dataset: {},
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

test("load momentum renders percent and state label when data is available", () => {
  const elements = {
    loadChart: createFakeElement(),
    loadMomentumCard: createFakeElement(),
    loadMomentumValue: createFakeElement(),
    loadMomentumLabel: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderLoadTrendCard(
      [
        { date: "2026-03-12", dailyLoad: 24, load7d: 80, load28d: 70 },
        { date: "2026-03-13", dailyLoad: 30, load7d: 90, load28d: 72 },
      ],
      "2026-03-13",
      { value: 0.14, label: "Rising" },
    );
  });

  assert.equal(elements.loadMomentumValue.textContent, "+14.0%");
  assert.equal(elements.loadMomentumLabel.textContent, "Rising");
  assert.equal(elements.loadMomentumCard.dataset.tone, "rising");
  assert.match(elements.loadChart.innerHTML, /<rect/);
  assert.match(elements.loadChart.innerHTML, /<path/);
  assert.equal(elements.loadChart.dataset.empty, "false");
});

test("load momentum renders a no-data state cleanly", () => {
  const elements = {
    loadChart: createFakeElement(),
    loadMomentumCard: createFakeElement(),
    loadMomentumValue: createFakeElement(),
    loadMomentumLabel: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderLoadTrendCard(
      [{ date: "2026-03-13", dailyLoad: 12, load7d: 45, load28d: 52 }],
      "2026-03-13",
      null,
    );
  });

  assert.equal(elements.loadMomentumValue.textContent, "No data");
  assert.equal(elements.loadMomentumLabel.textContent, "Need a complete previous 7d window.");
  assert.equal(elements.loadMomentumCard.dataset.tone, "neutral");
});

test("load channel chart renders a clear empty state when history is insufficient", () => {
  const chart = buildLoadChannelMarkup(
    [{ date: "2026-03-13", dailyLoad: null, load7d: null, load28d: null }],
    "2026-03-13",
  );

  assert.equal(chart.empty, true);
  assert.match(chart.markup, /Not enough load history for the load channel chart\./);
});
