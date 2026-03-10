import { el, safeHtml } from "../../lib/formatters.js";

export function renderAvoidTodayPanel(items) {
  const target = el("avoidTodayList");
  if (!items || !items.length) {
    target.innerHTML = '<div class="muted-copy">Nothing explicitly blocked today.</div>';
    return;
  }

  target.innerHTML = items.map((item) => `
    <article class="avoid-item">
      <span class="avoid-mark">Avoid</span>
      <span>${safeHtml(item)}</span>
    </article>
  `).join("");
}
