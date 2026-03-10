import { safeHtml } from "../../lib/formatters.js";

export function renderRecoveryStatusCard(status) {
  return `
    <article class="snapshot-card" data-tone="${safeHtml(status?.tone || "neutral")}">
      <span>Recovery</span>
      <strong>${safeHtml(status?.value || "-")}</strong>
    </article>
  `;
}
