import { renderRecommendationChips } from "./RecommendationChips.js";
import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTrainingDecisionCard({ payload }) {
  const decision = payload?.decision || {};
  const targetDay = payload?.today?.recommendationDay || payload?.date;
  const targetWindow = payload?.today?.recommendationDay && payload.today.recommendationDay !== payload.date
    ? "Tomorrow"
    : "Today";

  el("decisionTargetDay").textContent = `${targetWindow}: ${safeText(targetDay)}`;
  el("decisionTargetMeta").textContent = `Focus date ${safeText(payload?.date)}. Recommendation applies to ${safeText(targetDay)}.`;
  el("decisionLevel").textContent = safeText(decision.primaryRecommendation);
  el("decisionScore").textContent = formatNumber(decision.recoveryScore, 2);
  el("decisionReadiness").textContent = formatNumber(payload?.today?.readiness, 0);
  el("decisionSummary").textContent = safeText(decision.summaryText, "No recommendation available.");
  el("decisionConclusion").textContent = safeText(decision.strengthGuidance, "Decision guidance pending.");
  el("decisionStatusChips").innerHTML = renderRecommendationChips(decision.statusChips || []);
  setPanelTone(el("decisionHero"), toneForRecommendation(decision.primaryRecommendation));
}

function toneForRecommendation(recommendation) {
  if (recommendation === "VO2max OK" || recommendation === "Threshold OK") {
    return "positive";
  }
  if (recommendation === "Moderate only" || recommendation === "Easy Aerobic" || recommendation === "Strength OK") {
    return "warning";
  }
  if (recommendation === "Recovery day" || recommendation === "Avoid intensity") {
    return "critical";
  }
  return "neutral";
}
