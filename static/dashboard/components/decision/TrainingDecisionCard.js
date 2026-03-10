import { renderRecommendationChips } from "./RecommendationChips.js";
import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTrainingDecisionCard({ payload }) {
  const decision = payload?.decision || {};
  const targetDay = payload?.today?.recommendationDay || payload?.date;
  const targetWindow = payload?.today?.recommendationDay && payload.today.recommendationDay !== payload.date
    ? "Tomorrow"
    : "Today";
  const headline = buildDecisionHeadline(decision.primaryRecommendation);
  const subline = buildDecisionSubline(decision);
  const guidance = buildDecisionGuidance(decision);

  el("decisionTargetDay").textContent = `${targetWindow}: ${safeText(targetDay)}`;
  el("decisionTargetMeta").textContent = `Focus Day ${safeText(payload?.date)}. Recommendation for ${safeText(targetDay)}.`;
  el("decisionLevel").textContent = headline;
  el("decisionScore").textContent = formatNumber(decision.recoveryScore, 2);
  el("decisionReadiness").textContent = formatNumber(payload?.today?.readiness, 0);
  el("decisionSummary").textContent = subline;
  el("decisionConclusion").textContent = guidance;
  el("decisionConclusion").hidden = !guidance;
  el("decisionStatusChips").innerHTML = renderRecommendationChips(decision.statusChips || []);
  setPanelTone(el("decisionHero"), toneForRecommendation(decision.primaryRecommendation));
}

function toneForRecommendation(recommendation) {
  if (recommendation === "VO2max OK" || recommendation === "Threshold OK" || recommendation === "Strength OK") {
    return "positive";
  }
  if (recommendation === "Moderate only" || recommendation === "Easy Aerobic") {
    return "warning";
  }
  if (recommendation === "Recovery day" || recommendation === "Avoid intensity") {
    return "critical";
  }
  return "neutral";
}

function buildDecisionHeadline(primaryRecommendation) {
  return {
    "Threshold OK": "Threshold Training Recommended",
    "VO2max OK": "VO2 Training Recommended",
    "Moderate only": "Moderate Training Only",
    "Easy Aerobic": "Easy Training Recommended",
    "Recovery day": "Recovery Day Recommended",
    "Avoid intensity": "Recovery Day Recommended",
    "Strength OK": "Strength Training Recommended",
  }[primaryRecommendation] || safeText(primaryRecommendation, "No Recommendation Yet");
}

function buildDecisionSubline(decision) {
  const recovery = humanizeRecoveryStatus(decision.recoveryStatus);
  const load = humanizeLoadStatus(decision.loadTolerance);
  const intensity = humanizeIntensity(decision.intensityPermission);

  if (!recovery && !load && !intensity) {
    return "Sync data to load your plan.";
  }

  return [
    recovery ? `Recovery ${recovery}` : null,
    load ? `Load ${load}` : null,
    intensity,
  ].filter(Boolean).join(" | ");
}

function buildDecisionGuidance(decision) {
  if (decision?.strengthGuidance) {
    return safeText(decision.strengthGuidance);
  }
  return decision?.primaryRecommendation ? "" : "Recommendation updates after the next sync.";
}

function humanizeRecoveryStatus(status) {
  return {
    Good: "good",
    Stable: "stable",
    Borderline: "borderline",
    Poor: "poor",
  }[status] || "";
}

function humanizeLoadStatus(status) {
  return {
    High: "high",
    Normal: "normal",
    Reduced: "reduced",
    Low: "low",
  }[status] || "";
}

function humanizeIntensity(intensityPermission) {
  return {
    vo2: "VO2 allowed",
    threshold: "Threshold allowed",
    moderate: "Moderate only",
    none: "Avoid intensity",
  }[intensityPermission] || "";
}
