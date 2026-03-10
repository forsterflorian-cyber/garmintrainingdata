import { safeHtml } from "../../lib/formatters.js";

export function renderLoadToleranceCard(status) {
  return `
    <article class="snapshot-card" data-tone="${safeHtml(status?.tone || "neutral")}">
      <span>Load</span>
      <strong>${safeHtml(status?.value || "-")}</strong>
    </article>
  `;
}
