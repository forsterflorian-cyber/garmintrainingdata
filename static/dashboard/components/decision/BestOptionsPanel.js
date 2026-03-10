import { el, safeHtml } from "../../lib/formatters.js";

export function renderBestOptionsPanel(options, { selectedType = null } = {}) {
  const target = el("decisionSessionGrid");
  const buttonTarget = el("plannedSessionButtons");

  if (!options || !options.length) {
    target.innerHTML = '<div class="muted-copy">No session options available.</div>';
    buttonTarget.innerHTML = "";
    return;
  }

  target.innerHTML = options.map((option, index) => `
    <article class="decision-session-card" data-selected="${option.type === selectedType ? "true" : "false"}">
      <p class="eyebrow">Option ${index + 1}</p>
      <h4>${safeHtml(option.label)}</h4>
      <p class="session-details">${safeHtml(option.details)}</p>
      <div class="session-meta">
        <span class="session-tag">${safeHtml(option.sportTag)}</span>
        <span class="session-fatigue">${safeHtml(option.fatigueLevel)} fatigue</span>
      </div>
    </article>
  `).join("");

  buttonTarget.innerHTML = options.map((option) => `
    <button class="btn ${option.type === selectedType ? "btn-primary" : "btn-secondary"} plan-option-btn" type="button" data-session-type="${safeHtml(option.type)}">
      ${option.type === selectedType ? "Planned: " : "Select: "}${safeHtml(option.label)}
    </button>
  `).join("");
}
