import { safeHtml } from "../../lib/formatters.js";

export function renderRecommendationChips(chips) {
  if (!chips || !chips.length) {
    return '<div class="muted-copy">No decision badges available.</div>';
  }

  return chips.map((chip) => `
    <article class="recommendation-chip" data-tone="${safeHtml(chip.tone || "neutral")}">
      <span>${safeHtml(chip.label)}</span>
      <strong>${safeHtml(chip.value)}</strong>
    </article>
  `).join("");
}
