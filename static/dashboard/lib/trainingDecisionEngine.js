import { getSession, prioritizeForMode, sessionToBestOption } from "./sessionCatalog.js";

export function computeTrainingDecisionFromState(state, options = {}) {
  const context = resolveTrainingDecisionContext(state);
  return assembleTrainingDecision({
    mode: state?.mode || "hybrid",
    recovery: context.recovery,
    loadTolerance: context.loadTolerance,
    intensity: applyIntensityOverride(context.intensity, options.intensityOverride),
  });
}

export function resolveTrainingDecisionContext(state) {
  const recovery = buildRecoveryLayerFromScore(state?.recoveryScore);
  const loadTolerance = computeLoadToleranceLayer(state);
  const intensity = computeIntensityPermission({
    recovery,
    loadTolerance,
    load: state,
    comparisons: state?.comparisons || {},
    readiness: state?.readiness,
    restingHrDeltaBpm: state?.restingHrDeltaBpm,
  });
  return { recovery, loadTolerance, intensity };
}

export function assembleTrainingDecision({ mode = "hybrid", recovery, loadTolerance, intensity }) {
  const strength = computeStrengthPermission({
    recovery,
    intensityPermission: intensity.value,
    loadTolerance,
  });
  const primaryRecommendation = pickPrimaryRecommendation({
    recovery,
    loadTolerance,
    intensity,
    strength,
  });
  const bestOptions = buildBestOptions({
    intensityPermission: intensity.value,
    recoveryStatus: recovery.status,
    primaryRecommendation,
    strengthPermission: strength.value,
    mode,
  });

  return {
    recoveryScore: recovery.score,
    recoveryStatus: recovery.status,
    loadToleranceScore: loadTolerance.score,
    loadTolerance: loadTolerance.status,
    intensityPermission: intensity.value,
    primaryRecommendation,
    bestOptions,
    avoid: buildAvoidList({
      recovery,
      loadTolerance,
      intensity,
      strength,
    }),
    strengthGuidance: strength.label,
    debug: {
      recoveryScore: recovery.score,
      loadToleranceScore: loadTolerance.score,
      ratio7to28: stateValueOrNull(loadTolerance.sourceRatio),
      hardSessionsLast3d: stateValueOrNull(loadTolerance.sourceHardSessions),
      selectedRulePath: [
        `recovery=${recovery.status}`,
        `loadTolerance=${loadTolerance.status}`,
        ...intensity.trace,
        `strength=${strength.value}`,
      ],
    },
  };
}

export function buildRecoveryLayerFromScore(score) {
  const normalizedScore = clampNumber(score, -1, 1, -0.05);
  return {
    score: roundTo(normalizedScore, 2),
    status: recoveryStatusFromScore(normalizedScore),
    tone: toneForRecoveryStatus(recoveryStatusFromScore(normalizedScore)),
    trace: [`forecast recovery score ${roundTo(normalizedScore, 2)}`],
  };
}

export function computeLoadToleranceLayer(load) {
  const trace = [];
  let score = 0.0;
  const ratio = safeNumber(load?.loadRatio ?? load?.ratio7to28);
  const hardSessionsLast3d = integerOrZero(load?.hardSessionsLast3d);
  const veryHighYesterdayLoad = Boolean(load?.veryHighYesterdayLoad);

  if (ratio === null) {
    trace.push("ratio: missing");
  } else if (ratio < 0.8) {
    score += 0.25;
    trace.push("ratio underloaded: +0.25");
  } else if (ratio <= 1.1) {
    score += 0.10;
    trace.push("ratio normal: +0.10");
  } else if (ratio <= 1.3) {
    score -= 0.15;
    trace.push("ratio elevated: -0.15");
  } else {
    score -= 0.40;
    trace.push("ratio high: -0.40");
  }

  if (hardSessionsLast3d <= 0) {
    score += 0.20;
    trace.push("no hard sessions in last 3d: +0.20");
  } else if (hardSessionsLast3d === 1) {
    trace.push("one hard session in last 3d: +0.00");
  } else {
    score -= 0.30;
    trace.push("2+ hard sessions in last 3d: -0.30");
  }

  if (veryHighYesterdayLoad) {
    score -= 0.20;
    trace.push("very high yesterday load: -0.20");
  }

  const roundedScore = roundTo(score, 2);
  return {
    score: roundedScore,
    status: loadToleranceStatusFromScore(roundedScore),
    tone: toneForLoadTolerance(loadToleranceStatusFromScore(roundedScore)),
    trace,
    sourceRatio: ratio,
    sourceHardSessions: hardSessionsLast3d,
  };
}

export function computeIntensityPermission({
  recovery,
  loadTolerance,
  load,
  comparisons = {},
  readiness = null,
  restingHrDeltaBpm = null,
}) {
  const trace = [];
  const ratio = safeNumber(load?.loadRatio ?? load?.ratio7to28);
  const hrvDeltaPct = safeNumber(comparisons?.hrvDeltaPct);
  const sleepDeltaPct = safeNumber(comparisons?.sleepDeltaPct);
  const respirationDeltaPct = safeNumber(comparisons?.respirationDeltaPct);
  const effectiveRestingHrDeltaBpm = safeNumber(restingHrDeltaBpm);
  const qualityYesterday = ["threshold", "vo2"].includes(load?.yesterdaySessionType);

  const hrvSuppressed = hrvDeltaPct !== null && hrvDeltaPct <= -12.0;
  const hrvNotTooLow = hrvDeltaPct === null || hrvDeltaPct >= -5.0;
  const rhrElevated = effectiveRestingHrDeltaBpm !== null && effectiveRestingHrDeltaBpm >= 3.0;
  const rhrOkForVo2 = effectiveRestingHrDeltaBpm === null || effectiveRestingHrDeltaBpm <= 3.0;
  const sleepVeryLow = sleepDeltaPct !== null && sleepDeltaPct <= -15.0;
  const respirationElevated = respirationDeltaPct !== null && respirationDeltaPct >= 5.0;
  const readinessScore = readiness === null || readiness === undefined ? null : Number(readiness);

  if (recovery.status === "Poor") {
    trace.push("recovery poor -> no intensity");
    return { value: "none", label: "none", tone: "critical", trace, recoveryDay: true };
  }
  if (ratio !== null && ratio > 1.3) {
    trace.push("ratio > 1.3 -> no intensity");
    return { value: "none", label: "none", tone: "critical", trace, recoveryDay: true };
  }
  if (hrvSuppressed && rhrElevated) {
    trace.push("HRV strongly suppressed plus RHR elevated -> no intensity");
    return { value: "none", label: "none", tone: "critical", trace, recoveryDay: true };
  }
  if (sleepVeryLow && respirationElevated) {
    trace.push("sleep very low plus respiration elevated -> no intensity");
    return { value: "none", label: "none", tone: "critical", trace, recoveryDay: true };
  }

  if (
    recovery.status === "Good"
    && ["High", "Normal"].includes(loadTolerance.status)
    && !qualityYesterday
    && (readinessScore === null || readinessScore >= 65)
    && hrvNotTooLow
    && rhrOkForVo2
  ) {
    trace.push("VO2 allowed");
    return { value: "vo2", label: "VO2", tone: "positive", trace, recoveryDay: false };
  }

  const consecutiveQualityAllowed = recovery.status === "Good" && (ratio === null || ratio < 1.0);
  if (
    ["Good", "Stable"].includes(recovery.status)
    && loadTolerance.status !== "Low"
    && (!qualityYesterday || consecutiveQualityAllowed)
  ) {
    trace.push("threshold allowed");
    return { value: "threshold", label: "Threshold", tone: "warning", trace, recoveryDay: false };
  }

  if (recovery.status !== "Poor" && loadTolerance.status !== "Low") {
    trace.push("moderate allowed");
    return { value: "moderate", label: "Moderate", tone: "warning", trace, recoveryDay: false };
  }

  trace.push("mixed signals -> no quality");
  return { value: "none", label: "none", tone: "critical", trace, recoveryDay: false };
}

export function computeStrengthPermission({ recovery, intensityPermission, loadTolerance }) {
  if (recovery.status === "Poor") {
    return { value: "avoid_heavy", label: "Avoid heavy lower-body strength" };
  }
  if (["vo2", "threshold"].includes(intensityPermission)) {
    return { value: "light_accessory", label: "Strength only as light accessory" };
  }
  if (["Good", "Stable"].includes(recovery.status) && ["High", "Normal"].includes(loadTolerance.status)) {
    return { value: "hypertrophy_ok", label: "Hypertrophy strength is acceptable" };
  }
  return { value: "maintenance_ok", label: "Strength maintenance only" };
}

export function pickPrimaryRecommendation({ recovery, loadTolerance, intensity, strength }) {
  if (intensity.recoveryDay) {
    if (loadTolerance.status === "Low") {
      return "Avoid intensity";
    }
    return "Recovery day";
  }
  if (intensity.value === "vo2") {
    return "VO2max OK";
  }
  if (intensity.value === "threshold") {
    return "Threshold OK";
  }
  if (intensity.value === "moderate") {
    if (strength.value === "hypertrophy_ok" && ["Reduced", "Normal"].includes(loadTolerance.status)) {
      return "Strength OK";
    }
    return "Moderate only";
  }
  if (["Borderline", "Poor"].includes(recovery.status) || ["Reduced", "Low"].includes(loadTolerance.status)) {
    return "Easy Aerobic";
  }
  return "Easy Aerobic";
}

export function buildBestOptions({
  intensityPermission,
  recoveryStatus,
  primaryRecommendation,
  strengthPermission,
  mode,
}) {
  let optionIds;
  if (["Recovery day", "Avoid intensity"].includes(primaryRecommendation)) {
    optionIds = ["walk_mobility", "easy_spin", "no_structured_intensity"];
  } else if (intensityPermission === "vo2") {
    optionIds = ["vo2_run", "vo2_ride", "threshold_alternative"];
  } else if (intensityPermission === "threshold") {
    optionIds = ["threshold_run", "threshold_ride", "moderate_endurance"];
  } else if (intensityPermission === "moderate") {
    if (strengthPermission === "hypertrophy_ok" && mode === "strength") {
      optionIds = ["strength_hypertrophy", "moderate_ride", "moderate_run"];
    } else if (primaryRecommendation === "Strength OK") {
      optionIds = ["strength_hypertrophy", "moderate_ride", "moderate_run"];
    } else {
      optionIds = ["moderate_ride", "moderate_run", "strength_maintenance"];
    }
  } else if (recoveryStatus === "Poor") {
    optionIds = ["walk_mobility", "easy_spin", "no_structured_intensity"];
  } else {
    optionIds = ["easy_ride", "easy_run", "strength_light"];
  }

  return prioritizeForMode(optionIds, mode)
    .slice(0, 3)
    .map((optionId) => getSession(optionId))
    .filter(Boolean)
    .map((session) => sessionToBestOption(session));
}

export function buildAvoidList({ recovery, loadTolerance, intensity, strength }) {
  const avoid = [];

  if (intensity.value !== "vo2") {
    avoid.push("VO2 intervals");
  }
  if (!["vo2", "threshold"].includes(intensity.value)) {
    avoid.push("Threshold work");
  }
  if (["Reduced", "Low"].includes(loadTolerance.status)) {
    avoid.push("Extra volume on top of current load");
  }
  if (strength.value !== "hypertrophy_ok") {
    avoid.push("Heavy lower-body strength");
  }
  if (recovery.status === "Poor") {
    avoid.push("Any session that pushes pace or power");
  }

  return avoid.filter((item, index) => avoid.indexOf(item) === index).slice(0, 3);
}

export function recoveryStatusFromScore(score) {
  if (score >= 0.35) {
    return "Good";
  }
  if (score >= 0.10) {
    return "Stable";
  }
  if (score >= -0.15) {
    return "Borderline";
  }
  return "Poor";
}

export function loadToleranceStatusFromScore(score) {
  if (score >= 0.20) {
    return "High";
  }
  if (score >= -0.05) {
    return "Normal";
  }
  if (score >= -0.30) {
    return "Reduced";
  }
  return "Low";
}

export function toneForRecoveryStatus(status) {
  return {
    Good: "positive",
    Stable: "warning",
    Borderline: "warning",
    Poor: "critical",
  }[status] || "neutral";
}

export function toneForLoadTolerance(status) {
  return {
    High: "positive",
    Normal: "positive",
    Reduced: "warning",
    Low: "critical",
  }[status] || "neutral";
}

function applyIntensityOverride(intensity, override) {
  if (!override) {
    return intensity;
  }
  const trace = [...(intensity.trace || []), ...(override.trace || [])];
  return {
    ...intensity,
    ...override,
    trace,
  };
}

function clampNumber(value, min, max, fallback) {
  const numeric = safeNumber(value);
  if (numeric === null) {
    return fallback;
  }
  return Math.max(min, Math.min(max, numeric));
}

function integerOrZero(value) {
  return Number.isFinite(Number(value)) ? Math.max(0, Math.round(Number(value))) : 0;
}

function roundTo(value, digits) {
  const factor = 10 ** digits;
  return Math.round(Number(value) * factor) / factor;
}

function safeNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

function stateValueOrNull(value) {
  return value === undefined ? null : value;
}
