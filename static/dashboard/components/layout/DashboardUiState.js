import { el } from "../../lib/formatters.js";

export const TRAINING_FOCUS_COPY = Object.freeze({
  hybrid: {
    label: "Hybrid",
    description: "balanced endurance + strength",
  },
  run: {
    label: "Run",
    description: "running-focused",
  },
  bike: {
    label: "Bike",
    description: "cycling-focused",
  },
  strength: {
    label: "Strength",
    description: "strength-focused",
  },
});

export function describeTrainingFocus(mode = "hybrid") {
  return TRAINING_FOCUS_COPY[mode] || TRAINING_FOCUS_COPY.hybrid;
}

export function syncTrainingFocusHelp(mode = "hybrid") {
  const select = el("modeSelect");
  const help = el("modeHelpText");
  const copy = describeTrainingFocus(mode);

  if (select) {
    select.value = mode in TRAINING_FOCUS_COPY ? mode : "hybrid";
    select.title = `${copy.label} = ${copy.description}`;
  }

  if (help) {
    help.textContent = `${copy.label} = ${copy.description}`;
  }
}

export function setDashboardLoadingState(isLoading) {
  const stage = el("dashboardStage");
  const overlay = el("dashboardLoadingOverlay");
  const loading = Boolean(isLoading);

  if (stage) {
    stage.dataset.loading = loading ? "true" : "false";
    stage.setAttribute("aria-busy", loading ? "true" : "false");
  }

  if (overlay) {
    overlay.hidden = !loading;
    overlay.setAttribute("aria-hidden", loading ? "false" : "true");
  }
}
