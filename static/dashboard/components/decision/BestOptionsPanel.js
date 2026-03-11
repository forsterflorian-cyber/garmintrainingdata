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
        <div class="session-card-title">
          <p class="eyebrow">Option ${index + 1}</p>
          <h4>${safeHtml(option.label)}</h4>
        </div>
        <span class="session-selection-state">${option.type === selectedType ? "Selected" : "Preview"}</span>
      </div>
      <p class="session-details">${safeHtml(option.details)}</p>
      <div class="session-card-foot">
        <span class="session-summary-tag">${safeHtml(compactDescriptor(option))}</span>
      </div>
    </button>
  `).join("");
}

function compactDescriptor(option) {
  const segments = [option?.sportTag, option?.fatigueLevel]
    .filter(Boolean)
    .map((value) => String(value)
      .split(/[-_\s]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" "));

  return segments.join(" / ") || "Plan option";
}
