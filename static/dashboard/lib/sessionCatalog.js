const SESSION_CATALOG = {
  recovery: [
    {
      id: "walk_mobility",
      label: "Walk / Mobility",
      details: "20-40 min walk plus 10-15 min mobility",
      sportTag: "recovery",
      fatigueCost: 0.1,
      forecastCategory: "recovery",
    },
    {
      id: "easy_spin",
      label: "Easy Spin",
      details: "30-45 min very easy bike, all Z1",
      sportTag: "bike",
      fatigueCost: 0.2,
      forecastCategory: "recovery",
    },
    {
      id: "no_structured_intensity",
      label: "No Structured Intensity",
      details: "Keep the day unstructured and light",
      sportTag: "recovery",
      fatigueCost: 0.1,
      forecastCategory: "recovery",
    },
  ],
  easy: [
    {
      id: "easy_run",
      label: "Easy Run",
      details: "30-45 min easy aerobic, conversational only",
      sportTag: "run",
      fatigueCost: 0.2,
      forecastCategory: "easy",
    },
    {
      id: "easy_ride",
      label: "Easy Ride",
      details: "45-60 min smooth Z1/Z2 ride",
      sportTag: "bike",
      fatigueCost: 0.2,
      forecastCategory: "easy",
    },
    {
      id: "strength_light",
      label: "Mobility / Strength Light",
      details: "20-30 min light accessory or mobility only",
      sportTag: "strength",
      fatigueCost: 0.2,
      forecastCategory: "light_strength",
    },
  ],
  moderate: [
    {
      id: "moderate_run",
      label: "Moderate Run",
      details: "45-70 min controlled aerobic endurance",
      sportTag: "run",
      fatigueCost: 0.4,
      forecastCategory: "moderate",
    },
    {
      id: "moderate_ride",
      label: "Moderate Ride",
      details: "60-90 min Z2 with only low Z3 exposure",
      sportTag: "bike",
      fatigueCost: 0.4,
      forecastCategory: "moderate",
    },
    {
      id: "strength_maintenance",
      label: "Strength Maintenance",
      details: "2-3 controlled full-body rounds, no grinding",
      sportTag: "strength",
      fatigueCost: 0.3,
      forecastCategory: "light_strength",
    },
  ],
  threshold: [
    {
      id: "threshold_run",
      label: "Threshold Run",
      details: "2 x 10-15 min around LT with full control",
      sportTag: "run",
      fatigueCost: 0.7,
      forecastCategory: "threshold",
    },
    {
      id: "threshold_ride",
      label: "Threshold Ride",
      details: "2 x 12 min around FTP",
      sportTag: "bike",
      fatigueCost: 0.7,
      forecastCategory: "threshold",
    },
    {
      id: "moderate_endurance",
      label: "Moderate Endurance",
      details: "45-75 min controlled aerobic work",
      sportTag: "hybrid",
      fatigueCost: 0.4,
      forecastCategory: "moderate",
    },
  ],
  vo2: [
    {
      id: "vo2_run",
      label: "VO2 Run",
      details: "5 x 3 min @ VO2 pace",
      sportTag: "run",
      fatigueCost: 0.9,
      forecastCategory: "vo2",
    },
    {
      id: "vo2_ride",
      label: "VO2 Ride",
      details: "6 x 2 min @ 120% FTP",
      sportTag: "bike",
      fatigueCost: 0.9,
      forecastCategory: "vo2",
    },
    {
      id: "threshold_alternative",
      label: "Threshold Alternative",
      details: "Run 2 x 10 min or Bike 2 x 12 min steady threshold",
      sportTag: "hybrid",
      fatigueCost: 0.7,
      forecastCategory: "threshold",
    },
  ],
  strength: [
    {
      id: "strength_hypertrophy",
      label: "Strength Hypertrophy",
      details: "3-4 main sets, stop 1-2 reps before failure",
      sportTag: "strength",
      fatigueCost: 0.6,
      forecastCategory: "heavy_strength",
    },
    {
      id: "strength_maintenance",
      label: "Strength Maintenance",
      details: "2-3 rounds, low soreness target",
      sportTag: "strength",
      fatigueCost: 0.3,
      forecastCategory: "light_strength",
    },
  ],
};

export const SESSION_CATEGORY_PROFILES = {
  recovery: { fatigueCost: 0.1, loadImpact: 0.1, qualityFlag: false },
  easy: { fatigueCost: 0.2, loadImpact: 0.2, qualityFlag: false },
  moderate: { fatigueCost: 0.4, loadImpact: 0.4, qualityFlag: false },
  threshold: { fatigueCost: 0.7, loadImpact: 0.7, qualityFlag: true },
  vo2: { fatigueCost: 0.9, loadImpact: 0.9, qualityFlag: true },
  heavy_strength: { fatigueCost: 0.6, loadImpact: 0.5, qualityFlag: false },
  light_strength: { fatigueCost: 0.25, loadImpact: 0.2, qualityFlag: false },
};

export const QUALITY_SESSION_CATEGORIES = new Set(["threshold", "vo2"]);

const SESSION_INDEX = Object.fromEntries(
  Object.values(SESSION_CATALOG)
    .flat()
    .map((session) => [session.id, session]),
);

export function fatigueLabel(cost) {
  if (Number(cost) >= 0.8) {
    return "high";
  }
  if (Number(cost) >= 0.5) {
    return "moderate-high";
  }
  if (Number(cost) >= 0.3) {
    return "moderate";
  }
  return "low";
}

export function getSession(sessionId) {
  const session = SESSION_INDEX[sessionId];
  if (!session) {
    return null;
  }
  return {
    ...session,
    fatigueLabel: fatigueLabel(session.fatigueCost),
  };
}

export function sessionCategoryForType(sessionType) {
  if (!sessionType) {
    return null;
  }
  if (SESSION_CATEGORY_PROFILES[sessionType]) {
    return sessionType;
  }
  return SESSION_INDEX[sessionType]?.forecastCategory || null;
}

export function forecastProfileForSessionType(sessionType) {
  const category = sessionCategoryForType(sessionType);
  if (!category) {
    return null;
  }
  const session = SESSION_INDEX[sessionType] || null;
  return {
    category,
    fatigueCost: session?.fatigueCost ?? SESSION_CATEGORY_PROFILES[category].fatigueCost,
    loadImpact: SESSION_CATEGORY_PROFILES[category].loadImpact,
    qualityFlag: SESSION_CATEGORY_PROFILES[category].qualityFlag,
    type: session?.id || category,
    label: session?.label || category,
  };
}

export function isQualityCategory(category) {
  return QUALITY_SESSION_CATEGORIES.has(category);
}

export function isQualitySessionType(sessionType) {
  return isQualityCategory(sessionCategoryForType(sessionType));
}

export function sessionToBestOption(session) {
  return {
    type: session.id,
    label: session.label,
    details: session.details,
    fatigueCost: session.fatigueCost,
    fatigueLevel: session.fatigueLabel,
    sportTag: session.sportTag,
    forecastCategory: session.forecastCategory,
  };
}

export function prioritizeForMode(optionIds, mode) {
  if (!["run", "bike", "strength"].includes(mode)) {
    return optionIds;
  }

  const preferredTag = mode;
  return optionIds.slice().sort((leftId, rightId) => {
    const left = getSession(leftId);
    const right = getSession(rightId);
    const leftRank = modeRank(left?.sportTag, preferredTag);
    const rightRank = modeRank(right?.sportTag, preferredTag);
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return leftId.localeCompare(rightId);
  });
}

function modeRank(sportTag, preferredTag) {
  if (sportTag === preferredTag) {
    return 0;
  }
  if (sportTag === "hybrid") {
    return 1;
  }
  return 2;
}
