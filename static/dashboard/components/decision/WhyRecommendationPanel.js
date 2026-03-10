import { el, safeHtml } from "../../lib/formatters.js";

export function renderWhyRecommendationPanel(reasons) {
  const target = el("decisionWhyList");
  if (!reasons || !reasons.length) {
    target.innerHTML = '<div class="muted-copy">No recommendation trace available.</div>';
    return;
  }

  target.innerHTML = reasons.map((reason) => `
    <article class="why-item">
      <span class="why-bullet"></span>
      <span>${safeHtml(reason)}</span>
    </article>
  `).join("");
}
