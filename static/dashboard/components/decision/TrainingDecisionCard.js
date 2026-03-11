import { renderRecommendationChips } from "./RecommendationChips.js";
import { el, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTrainingDecisionCard({ payload, targetDayLabel = null, targetMeta = null }) {
  const decision = payload?.decision || {};
  const headline = buildDecisionHeadline(decision.primaryRecommendation);
  const subline = buildDecisionSubline(payload);
  const guidance = buildDecisionGuidance(decision);

  el("decisionTargetDay").textContent = safeText(targetDayLabel, payload?.date ? `Today: ${payload.date}` : "-");
  el("decisionTargetMeta").textContent = safeText(
    targetMeta,
    payload?.date ? `Decision anchored to ${safeText(payload.date)}.` : "No focus day loaded.",
  );
  el("decisionLevel").textContent = headline;
  el("decisionSummary").textContent = subline;
  el("decisionConclusion").textContent = guidance;
  el("decisionConclusion").hidden = !guidance;
  el("decisionStatusChips").innerHTML = renderRecommendationChips(primaryStatusChips(decision.statusChips || []));
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
    "Threshold OK": "Threshold Session Recommended",
    "VO2max OK": "VO2 Session Recommended",
    "Moderate only": "Moderate Training Only",
    "Easy Aerobic": "Easy Training Only",
    "Recovery day": "Recovery Day Recommended",
    "Avoid intensity": "Recovery Day Recommended",
    "Strength OK": "Strength Focus Recommended",
  }[primaryRecommendation] || safeText(primaryRecommendation, "No Recommendation Yet");
}

function buildDecisionSubline(payload) {
  const reasons = Array.isArray(payload?.decision?.why)
    ? payload.decision.why.filter((reason) => typeof reason === "string" && reason.trim())
    : [];
  if (reasons.length) {
    return reasons.slice(0, 2).join(" / ");
  }
  if (!payload?.decision?.summaryText) {
    return "Sync data to load your plan.";
  }
  return safeText(payload.decision.summaryText);
}

function buildDecisionGuidance(decision) {
  if (decision?.strengthGuidance) {
    return safeText(decision.strengthGuidance);
  }
  if (!decision?.primaryRecommendation) {
    return "Recommendation updates after the next sync.";
  }
  return {
    "Threshold OK": "Keep the rest of the session controlled around the quality work.",
    "VO2max OK": "Use the green light for intensity, but keep the session well structured.",
    "Moderate only": "Keep effort controlled and leave hard intervals for another day.",
    "Easy Aerobic": "Stay easy and use the session to support recovery.",
    "Recovery day": "Use easy movement only and keep overall strain low.",
    "Avoid intensity": "Skip hard load today and keep everything restorative.",
    "Strength OK": "Strength can lead today while endurance work stays moderate.",
  }[decision.primaryRecommendation] || "";
}

function primaryStatusChips(chips) {
  const preferredLabels = ["Recovery", "Load", "Intensity", "Confidence"];
  return preferredLabels
    .map((label) => chips.find((chip) => chip?.label === label))
    .filter(Boolean);
}
