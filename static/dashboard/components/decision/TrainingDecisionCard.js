import { renderRecommendationChips } from "./RecommendationChips.js";
import { el, formatNumber, safeText } from "../../lib/formatters.js";
import { setPanelTone } from "../layout/SectionCard.js";

export function renderTrainingDecisionCard({ payload }) {
  const decision = payload?.decision || {};
  const targetDay = payload?.today?.recommendationDay || payload?.date;
  const targetWindow = payload?.today?.recommendationDay && payload.today.recommendationDay !== payload.date
    ? "Tomorrow"
    : "Today";
  const focusDay = safeText(payload?.date);
  const recommendationDay = safeText(targetDay);
  const headline = buildDecisionHeadline(decision.primaryRecommendation);
  const subline = buildDecisionSubline(decision);
  const guidance = buildDecisionGuidance(decision);
  const recoveryCard = buildRecoveryCard(decision.recoveryStatus, decision.recoveryScore);
  const readinessCard = buildReadinessCard(payload?.today?.readiness);

  el("decisionTargetDay").textContent = `${targetWindow}: ${recommendationDay}`;
  el("decisionTargetMeta").textContent = payload?.date
    ? `Reviewing ${focusDay} / Decision for ${recommendationDay}`
    : "No focus day loaded.";
  el("decisionLevel").textContent = headline;
  el("decisionSummary").textContent = subline;
  el("decisionConclusion").textContent = guidance;
  el("decisionConclusion").hidden = !guidance;
  el("decisionRecoveryStatus").textContent = recoveryCard.status;
  el("decisionRecoveryMeta").textContent = recoveryCard.meta;
  el("decisionReadinessStatus").textContent = readinessCard.status;
  el("decisionReadinessMeta").textContent = readinessCard.meta;
  el("decisionStatusChips").innerHTML = renderRecommendationChips(decision.statusChips || []);
  setPanelTone(el("decisionHero"), toneForRecommendation(decision.primaryRecommendation));
  setPanelTone(el("decisionRecoveryCard"), recoveryCard.tone);
  setPanelTone(el("decisionReadinessCard"), readinessCard.tone);
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

function buildDecisionSubline(decision) {
  const recovery = shortRecoveryLine(decision.recoveryStatus);
  const load = shortLoadLine(decision.loadTolerance);
  const intensity = shortIntensityLine(decision.intensityPermission);

  if (!recovery && !load && !intensity) {
    return "Sync data to load your plan.";
  }

  return [recovery, load, intensity].filter(Boolean).join(" / ");
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

function buildRecoveryCard(status, score) {
  const detail = {
    Good: "Quality work supported",
    Stable: "Controlled load fits",
    Borderline: "Moderate training recommended",
    Poor: "Recovery day recommended",
  }[status];

  if (!detail) {
    return {
      status: "Waiting for sync",
      meta: "No recovery score yet",
      tone: "neutral",
    };
  }

  return {
    status: status === "Good" ? "Ready" : status,
    meta: `${detail} / score ${formatNumber(score, 2)}`,
    tone: toneForRecoveryStatus(status),
  };
}

function buildReadinessCard(readiness) {
  if (readiness === null || readiness === undefined || Number.isNaN(Number(readiness))) {
    return {
      status: "Waiting for sync",
      meta: "No readiness score yet",
      tone: "neutral",
    };
  }

  const numericReadiness = Number(readiness);
  let status = "Low";
  if (numericReadiness >= 75) {
    status = "Ready";
  } else if (numericReadiness >= 60) {
    status = "Moderate";
  } else if (numericReadiness >= 45) {
    status = "Cautious";
  }

  return {
    status,
    meta: `${formatNumber(numericReadiness, 0)} today`,
    tone: toneForReadiness(numericReadiness),
  };
}

function shortRecoveryLine(status) {
  return {
    Good: "Recovery strong",
    Stable: "Recovery steady",
    Borderline: "Recovery borderline",
    Poor: "Recovery low",
  }[status] || "";
}

function shortLoadLine(status) {
  return {
    High: "Load well supported",
    Normal: "Load balanced",
    Reduced: "Load reduced",
    Low: "Load restricted",
  }[status] || "";
}

function shortIntensityLine(intensityPermission) {
  return {
    vo2: "VO2 allowed",
    threshold: "Threshold allowed",
    moderate: "Moderate work only",
    none: "No hard intervals",
  }[intensityPermission] || "";
}

function toneForRecoveryStatus(status) {
  return {
    Good: "positive",
    Stable: "warning",
    Borderline: "warning",
    Poor: "critical",
  }[status] || "neutral";
}

function toneForReadiness(readiness) {
  if (readiness >= 75) {
    return "positive";
  }
  if (readiness >= 45) {
    return "warning";
  }
  return "critical";
}
