import { el, safeHtml } from "../../lib/formatters.js";

export function renderBestOptionsPanel(options, { selectedType = null } = {}) {
  const target = el("decisionSessionGrid");

  if (!options || !options.length) {
    target.innerHTML = '<div class="muted-copy">No session options available.</div>';
    return;
  }

  target.innerHTML = options.map((option, index) => `
    <button
      class="decision-session-card plan-option-card"
      type="button"
      data-session-type="${safeHtml(option.type)}"
      data-selected="${option.type === selectedType ? "true" : "false"}"
      aria-pressed="${option.type === selectedType ? "true" : "false"}"
    >
      <div class="session-card-head">
        <p class="eyebrow">Option ${index + 1}</p>
        <span class="session-selection-state">${option.type === selectedType ? "Selected" : "Preview"}</span>
      </div>
      <h4>${safeHtml(option.label)}</h4>
      <p class="session-details">${safeHtml(option.details)}</p>
      <div class="session-meta">
        <span class="session-tag">${safeHtml(option.sportTag)}</span>
        <span class="session-fatigue">${safeHtml(option.fatigueLevel)} fatigue</span>
      </div>
    </button>
  `).join("");
}
