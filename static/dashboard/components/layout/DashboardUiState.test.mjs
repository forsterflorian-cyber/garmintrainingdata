import test from "node:test";
import assert from "node:assert/strict";

import { describeTrainingFocus, setDashboardLoadingState, syncTrainingFocusHelp } from "./DashboardUiState.js";

function createFakeElement() {
  return {
    hidden: false,
    value: "",
    textContent: "",
    title: "",
    dataset: {},
    attributes: {},
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    getAttribute(name) {
      return this.attributes[name] || null;
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

test("describeTrainingFocus returns the expected helper copy", () => {
  assert.deepEqual(describeTrainingFocus("hybrid"), {
    label: "Hybrid",
    description: "Balanced endurance and strength training",
  });
  assert.deepEqual(describeTrainingFocus("unknown"), {
    label: "Hybrid",
    description: "Balanced endurance and strength training",
  });
});

test("setDashboardLoadingState toggles the dashboard overlay visibility", () => {
  const elements = {
    dashboardStage: createFakeElement(),
    dashboardLoadingOverlay: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    setDashboardLoadingState(true);
    assert.equal(elements.dashboardStage.dataset.loading, "true");
    assert.equal(elements.dashboardStage.getAttribute("aria-busy"), "true");
    assert.equal(elements.dashboardLoadingOverlay.hidden, false);
    assert.equal(elements.dashboardLoadingOverlay.getAttribute("aria-hidden"), "false");

    setDashboardLoadingState(false);
    assert.equal(elements.dashboardStage.dataset.loading, "false");
    assert.equal(elements.dashboardStage.getAttribute("aria-busy"), "false");
    assert.equal(elements.dashboardLoadingOverlay.hidden, true);
    assert.equal(elements.dashboardLoadingOverlay.getAttribute("aria-hidden"), "true");
  });
});

test("syncTrainingFocusHelp updates helper copy for the selected mode", () => {
  const elements = {
    modeSelect: createFakeElement(),
    modeHelpText: createFakeElement(),
  };

  withFakeDocument(elements, () => {
    syncTrainingFocusHelp("bike");
  });

  assert.equal(elements.modeSelect.value, "bike");
  assert.equal(elements.modeSelect.title, "Bike: Cycling-focused training");
  assert.equal(elements.modeHelpText.textContent, "Bike: Cycling-focused training");
});
