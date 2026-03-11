import { sessionCategoryForType } from "./sessionCatalog.js";

const SESSION_INTENSITY_RANK = Object.freeze({
  recovery: 0,
  easy: 1,
  light_strength: 1,
  moderate: 2,
  heavy_strength: 2,
  threshold: 3,
  vo2: 4,
});

export function compareCompletedSessionToDecision(sessionType, decision = {}, options = {}) {
  const sessionCategory = sessionCategoryForType(sessionType) || sessionType || null;
  const sessionRank = intensityRank(sessionCategory);
  const policy = recommendationPolicy(decision);
  const sessionSportTag = typeof options?.sportTag === "string" ? options.sportTag : null;

  if (sessionRank === null || !policy) {
    return null;
  }
  if (policy.alignedRanks.includes(sessionRank)) {
    return withFocusDetail({
      label: "Aligned with today's recommendation",
      tone: "positive",
    }, decision, sessionSportTag);
  }
  if (sessionRank > policy.allowedMaxRank) {
    const exceeded = sessionRank - policy.allowedMaxRank > 1 || (sessionRank >= 3 && policy.allowedMaxRank <= 1);
    return withFocusDetail({
      label: exceeded ? "Exceeded today's suggested limit" : "Slightly above recommended intensity",
      tone: exceeded ? "critical" : "warning",
    }, decision, sessionSportTag);
  }
  if (sessionRank > policy.targetRank) {
    return withFocusDetail({
      label: "Slightly above recommended intensity",
      tone: "warning",
    }, decision, sessionSportTag);
  }
  if (sessionRank < policy.minRecommendedRank) {
    return withFocusDetail({
      label: "Below recommended training load",
      tone: "neutral",
    }, decision, sessionSportTag);
  }
  return withFocusDetail({
    label: "Aligned with today's recommendation",
    tone: "positive",
  }, decision, sessionSportTag);
}

export function buildForecastContextCopy(session, { forecastInputMode = "preview" } = {}) {
  if (!session) {
    return forecastInputMode === "actual"
      ? "Based on today's completed session"
      : "Preview a session to update the forecast";
  }

  const sessionCopy = compactSessionCopy(session);
  return forecastInputMode === "actual"
    ? `Based on today's ${sessionCopy}`
    : `Previewing ${sessionCopy}`;
}

function recommendationPolicy(decision = {}) {
  switch (decision.primaryRecommendation) {
    case "Recovery day":
    case "Avoid intensity":
      return {
        alignedRanks: [0, 1],
        targetRank: 0,
        minRecommendedRank: 0,
        allowedMaxRank: 1,
      };
    case "Easy Aerobic":
      return {
        alignedRanks: [1],
        targetRank: 1,
        minRecommendedRank: 1,
        allowedMaxRank: 1,
      };
    case "Moderate only":
    case "Strength OK":
      return {
        alignedRanks: [2],
        targetRank: 2,
        minRecommendedRank: 2,
        allowedMaxRank: 2,
      };
    case "Threshold OK":
      return {
        alignedRanks: [3],
        targetRank: 3,
        minRecommendedRank: 3,
        allowedMaxRank: 3,
      };
    case "VO2max OK":
      return {
        alignedRanks: [4],
        targetRank: 4,
        minRecommendedRank: 4,
        allowedMaxRank: 4,
      };
    default:
      return null;
  }
}

function compactSessionCopy(session = {}) {
  const title = String(session.title || session.label || "session").trim();
  const durationMinutes = Number.isFinite(Number(session.durationMinutes))
    ? Math.round(Number(session.durationMinutes))
    : null;

  if (durationMinutes !== null && durationMinutes > 0) {
    return `${title} / ${durationMinutes} min`;
  }
  return title || "session";
}

function intensityRank(category) {
  return Number.isFinite(SESSION_INTENSITY_RANK[category]) ? SESSION_INTENSITY_RANK[category] : null;
}


function withFocusDetail(comparison, decision, sessionSportTag) {
  const preferredSportTag = preferredSportTagFromDecision(decision);
  if (!preferredSportTag || !sessionSportTag || preferredSportTag === "hybrid" || preferredSportTag === "recovery") {
    return comparison;
  }
  if (sessionSportTag === preferredSportTag) {
    return {
      ...comparison,
      detail: `${focusLabel(preferredSportTag)} focus matched this session.`,
    };
  }
  return {
    ...comparison,
    detail: `${focusLabel(preferredSportTag)} focus had priority today.`,
  };
}


function preferredSportTagFromDecision(decision = {}) {
  if (decision?.bestOptions?.[0]?.sportTag) {
    return decision.bestOptions[0].sportTag;
  }
  if (["run", "bike", "strength"].includes(decision?.mode)) {
    return decision.mode;
  }
  return null;
}


function focusLabel(sportTag) {
  return {
    run: "Run",
    bike: "Bike",
    strength: "Strength",
  }[sportTag] || "Mode";
}
