import test from "node:test";
import assert from "node:assert/strict";

import { renderReadinessTrendCard } from "./ReadinessTrendCard.js";

function createFakeElement() {
  return {
    innerHTML: "",
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

test("readiness chart renders an explicit empty state for sparse history", () => {
  const elements = {
    readinessChart: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    renderReadinessTrendCard([], "2026-03-11");
  });

  assert.equal(elements.readinessChart.dataset.empty, "true");
  assert.match(elements.readinessChart.innerHTML, /Not enough readiness history/);
});
