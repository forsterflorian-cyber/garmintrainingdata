import { forecastProfileForSessionType, getSession, isQualityCategory, sessionCategoryForType } from "./sessionCatalog.js";
import { assembleTrainingDecision, resolveTrainingDecisionContext } from "./trainingDecisionEngine.js";

const DEFAULT_VISIBLE_DAYS = 4;
const MAX_FORECAST_DAYS = 5;
const RECOVERY_REGEN = 0.35;
const LOAD_DECAY = 0.10;
const LOAD_IMPACT_SCALE = 0.25;
const MIN_RECOVERY_SCORE = -1.0;
const MAX_RECOVERY_SCORE = 1.0;
const MIN_LOAD_RATIO = 0.45;
const MAX_LOAD_RATIO = 1.85;
const QUALITY_BLOCKED_LOAD_RATIO = 1.15;
const QUALITY_REQUIRED_RECOVERY_SCORE = 0.10;

export function computeNextDaysOutlook({
  currentDecision,
  currentMetrics,
  currentLoad,
  currentComparisons,
  baseline,
  selectedSession,
  currentDate,
  mode = "hybrid",
  days = DEFAULT_VISIBLE_DAYS,
}) {
  const horizon = clampInteger(days, 1, MAX_FORECAST_DAYS, DEFAULT_VISIBLE_DAYS);
  const initialState = buildInitialSimulationState({
    currentDecision,
    currentMetrics,
    currentLoad,
    currentComparisons,
    baseline,
    currentDate,
    mode,
  });

  if (!initialState.available) {
    return unavailableOutlook(initialState.reason);
  }

  const selectedProfile = resolveSessionProfile(selectedSession);
  if (!selectedProfile) {
    return unavailableOutlook("Selected session missing.");
  }

  const selectedLabel = selectedSession?.label || getSession(selectedProfile.type)?.label || selectedProfile.label;
  let simulatedState = advanceSimulationState(initialState.state, selectedProfile);
  const forecastDays = [];
  const traceDays = [];

  for (let dayIndex = 0; dayIndex < horizon; dayIndex += 1) {
    const context = resolveTrainingDecisionContext(simulatedState);
    const intensityOverride = constrainForecastIntensity({
      state: simulatedState,
      rawIntensity: context.intensity,
      recovery: context.recovery,
      loadTolerance: context.loadTolerance,
    });
    const decision = assembleTrainingDecision({
      mode,
      recovery: context.recovery,
      loadTolerance: context.loadTolerance,
      intensity: intensityOverride ? applyIntensityTrace(context.intensity, intensityOverride) : context.intensity,
    });
    const defaultSession = chooseRepresentativeSession(decision, mode);
    const recommendation = outlookRecommendationForDecision(decision, defaultSession?.category);
    const label = forecastDayLabel(initialState.anchorDate, dayIndex + 1);
    const row = {
      label,
      date: addDays(initialState.anchorDate, dayIndex + 1),
      recommendation: recommendation.label,
      intensityPermission: recommendation.intensityPermission,
      recoveryStatus: decision.recoveryStatus,
      recoveryScore: decision.recoveryScore,
      tone: recommendation.tone,
      statusChip: outlookCapacityLabel(decision),
      defaultSessionCategory: defaultSession?.category || null,
      qualityBlocks: intensityOverride?.blocks || [],
      decision,
    };

    forecastDays.push(row);
    traceDays.push({
      label,
      recoveryScore: row.recoveryScore,
      recoveryStatus: row.recoveryStatus,
      loadRatio: simulatedState.loadRatio,
      rawIntensityPermission: context.intensity.value,
      finalIntensityPermission: decision.intensityPermission,
      qualityBlocks: intensityOverride?.blocks || [],
      recommendation: row.recommendation,
      defaultSessionCategory: row.defaultSessionCategory,
    });

    if (!defaultSession) {
      break;
    }
    simulatedState = advanceSimulationState(simulatedState, defaultSession);
  }

  if (!forecastDays.length) {
    return unavailableOutlook("Outlook unavailable.");
  }

  return {
    available: true,
    days: forecastDays,
    tomorrowImpact: buildTomorrowImpact(forecastDays[0]),
    trace: {
      initialState: summarizeState(initialState.state),
      selectedSessionCategory: selectedProfile.category,
      selectedSessionType: selectedProfile.type,
      selectedSessionLabel: selectedLabel,
      days: traceDays,
    },
  };
}

function buildInitialSimulationState({
  currentDecision,
  currentMetrics,
  currentLoad,
  currentComparisons,
  baseline,
  currentDate,
  mode,
}) {
  if (!currentDecision || safeNumber(currentDecision.recoveryScore) === null) {
    return { available: false, reason: "Decision data missing." };
  }
  if (!currentLoad) {
    return { available: false, reason: "Load data missing." };
  }

  const readiness = safeNumber(currentMetrics?.readiness);
  const restingHrDeltaBpm = deriveRestingHrDeltaBpm(currentMetrics, baseline);
  const conditionScore = deriveConditionScore({
    recoveryScore: currentDecision.recoveryScore,
    comparisons: currentComparisons,
    restingHrDeltaBpm,
  });

  return {
    available: true,
    anchorDate: currentDate || null,
    state: {
      mode,
      recoveryScore: clampNumber(currentDecision.recoveryScore, MIN_RECOVERY_SCORE, MAX_RECOVERY_SCORE, -0.05),
      loadRatio: safeNumber(currentLoad.ratio7to28),
      hardSessionsLast3d: clampInteger(currentLoad.hardSessionsLast3d, 0, 7, 0),
      hardSessionsLast7d: clampInteger(currentLoad.hardSessionsLast7d, 0, 7, 0),
      yesterdaySessionType: sessionCategoryForType(currentLoad.yesterdaySessionType) || currentLoad.yesterdaySessionType || null,
      lastSessionType: sessionCategoryForType(currentLoad.yesterdaySessionType) || currentLoad.yesterdaySessionType || null,
      lastSessionIntensity: sessionCategoryForType(currentLoad.yesterdaySessionType) || currentLoad.yesterdaySessionType || null,
      recentSessionCategories: seedRecentSessionCategories(currentLoad),
      recentQualityFlags: seedRecentQualityFlags(currentLoad),
      readiness,
      conditionScore,
      comparisons: deriveComparisonsFromCondition(conditionScore, currentComparisons),
      restingHrDeltaBpm,
      veryHighYesterdayLoad: Boolean(currentLoad.veryHighYesterdayLoad),
    },
  };
}

function resolveSessionProfile(selectedSession) {
  if (!selectedSession) {
    return null;
  }
  if (typeof selectedSession === "string") {
    return forecastProfileForSessionType(selectedSession);
  }
  return forecastProfileForSessionType(selectedSession.type) || forecastProfileForSessionType(selectedSession.id);
}

function chooseRepresentativeSession(decision, mode = "hybrid") {
  const bestOptions = decision?.bestOptions || [];
  
  // Filtere Optionen nach Modus
  const modeFilteredOptions = bestOptions.filter((option) => {
    if (!option?.type) return false;
    const session = getSession(option.type);
    if (!session) return false;
    
    // Bei "hybrid" alle Optionen erlauben
    if (mode === "hybrid") return true;
    
    // Bei spezifischem Modus nur passende Sportarten
    return session.sportTag === mode || session.sportTag === "hybrid";
  });

  // Verwende gefilterte Optionen oder Fallback auf alle
  const optionsToUse = modeFilteredOptions.length > 0 ? modeFilteredOptions : bestOptions;
  
  if (optionsToUse.length > 0) {
    // Wähle zufällig aus den passenden Optionen für mehr Vielfalt
    const randomIndex = Math.floor(Math.random() * Math.min(optionsToUse.length, 3));
    const selectedOption = optionsToUse[randomIndex];
    return resolveSessionProfile(selectedOption.type);
  }

  const fallbackCategory = categoryFromPrimaryRecommendation(decision?.primaryRecommendation, decision?.intensityPermission);
  if (!fallbackCategory) {
    return null;
  }
  return {
    category: fallbackCategory,
    fatigueCost: categoryDefaults(fallbackCategory).fatigueCost,
    loadImpact: categoryDefaults(fallbackCategory).loadImpact,
    qualityFlag: categoryDefaults(fallbackCategory).qualityFlag,
    type: fallbackCategory,
    label: fallbackCategory,
  };
}

function constrainForecastIntensity({ state, rawIntensity, recovery, loadTolerance }) {
  const blocks = [];
  let value = rawIntensity.value;
  let label = rawIntensity.label;
  let tone = rawIntensity.tone;
  let recoveryDay = rawIntensity.recoveryDay;

  const lastCompletedCategory = state.recentSessionCategories[0] || state.lastSessionType;
  const qualityDaysInLastTwo = countQualityFlags(state.recentQualityFlags.slice(0, 2));
  const loadElevated = state.loadRatio !== null && state.loadRatio >= QUALITY_BLOCKED_LOAD_RATIO;
  const qualityYesterday = isQualityCategory(lastCompletedCategory);

  if (value === "vo2" && lastCompletedCategory === "vo2") {
    value = "threshold";
    label = "Threshold";
    tone = "warning";
    recoveryDay = false;
    blocks.push("VO2 blocked after VO2");
  }
  if (["vo2", "threshold"].includes(value) && qualityDaysInLastTwo >= 2) {
    value = "moderate";
    label = "Moderate";
    tone = "warning";
    recoveryDay = false;
    blocks.push("quality blocked: 2 quality sessions in rolling 3-day window");
  }
  if (["vo2", "threshold"].includes(value) && state.recoveryScore < QUALITY_REQUIRED_RECOVERY_SCORE) {
    value = "moderate";
    label = "Moderate";
    tone = "warning";
    recoveryDay = false;
    blocks.push("quality blocked: recovery below 0.10");
  }
  if (["vo2", "threshold"].includes(value) && loadElevated) {
    value = "moderate";
    label = "Moderate";
    tone = "warning";
    recoveryDay = false;
    blocks.push("quality blocked: load remains elevated");
  }
  if (value === "moderate" && qualityYesterday && state.recoveryScore < 0.15) {
    value = "none";
    label = "none";
    tone = "warning";
    recoveryDay = false;
    blocks.push("post-quality recovery -> easy only");
  }
  if (recovery.status === "Poor") {
    value = "none";
    label = "none";
    tone = "critical";
    recoveryDay = true;
    blocks.push("poor recovery -> easy/recovery/light only");
  } else if (loadTolerance.status === "Low" && value !== "none") {
    value = "moderate";
    label = "Moderate";
    tone = "warning";
    recoveryDay = false;
    blocks.push("low load tolerance -> quality suppressed");
  }

  if (!blocks.length) {
    return null;
  }

  return {
    value,
    label,
    tone,
    recoveryDay,
    blocks,
    trace: blocks,
  };
}

function buildTomorrowImpact(day) {
  if (!day) {
    return {
      headline: "Choose today's session",
      text: "Select a session to update the best fit for tomorrow.",
      windowLabel: "Tomorrow's training window is waiting for today's session.",
      predictedScore: null,
      tone: "neutral",
    };
  }

  return {
    headline: tomorrowHeadlineForRecommendation(day.intensityPermission, day.recommendation),
    text: tomorrowTextForRecommendation(day.intensityPermission, day.recommendation),
    windowLabel: tomorrowWindowLabel(day.intensityPermission, day.recommendation),
    predictedScore: day.recoveryScore,
    tone: day.tone,
  };
}

function outlookRecommendationForDecision(decision, defaultCategory) {
  if (decision.primaryRecommendation === "Recovery day" || decision.primaryRecommendation === "Avoid intensity") {
    return { label: "Recovery likely", tone: "critical", intensityPermission: "none" };
  }
  if (decision.primaryRecommendation === "VO2max OK") {
    return { label: "Quality session possible", tone: "positive", intensityPermission: "vo2" };
  }
  if (decision.primaryRecommendation === "Threshold OK") {
    return { label: "Quality session possible", tone: "warning", intensityPermission: "threshold" };
  }
  if (decision.primaryRecommendation === "Strength OK" || defaultCategory === "heavy_strength") {
    return { label: "Strength session possible", tone: "warning", intensityPermission: "moderate" };
  }
  if (defaultCategory === "light_strength") {
    return { label: "Light strength fits best", tone: "warning", intensityPermission: "moderate" };
  }
  if (decision.primaryRecommendation === "Moderate only") {
    return { label: "Controlled training fits best", tone: "warning", intensityPermission: "moderate" };
  }
  if (decision.primaryRecommendation === "Easy Aerobic") {
    return { label: "Easy training fits best", tone: "warning", intensityPermission: "none" };
  }
  if (decision.intensityPermission === "threshold") {
    return { label: "Quality session possible", tone: "warning", intensityPermission: "threshold" };
  }
  if (decision.intensityPermission === "vo2") {
    return { label: "Quality session possible", tone: "positive", intensityPermission: "vo2" };
  }
  if (decision.intensityPermission === "moderate") {
    return { label: "Controlled training fits best", tone: "warning", intensityPermission: "moderate" };
  }
  return { label: "Easy training fits best", tone: "warning", intensityPermission: "none" };
}

function tomorrowHeadlineForRecommendation(intensityPermission, recommendation) {
  if (intensityPermission === "vo2" || recommendation.includes("Quality")) {
    return "Quality session possible";
  }
  if (intensityPermission === "threshold" || recommendation.includes("Threshold")) {
    return "Quality session possible";
  }
  if (recommendation.includes("Strength")) {
    return "Strength session possible";
  }
  if (intensityPermission === "moderate" || recommendation.includes("Controlled")) {
    return "Controlled training fits best";
  }
  return "Easy training fits best";
}

function tomorrowTextForRecommendation(intensityPermission, recommendation) {
  if (intensityPermission === "vo2" || recommendation.includes("Quality")) {
    return "Tomorrow's window can support a quality session if today's load stays controlled.";
  }
  if (recommendation.includes("Strength")) {
    return "Tomorrow looks best for leading with strength while endurance stays secondary.";
  }
  if (intensityPermission === "moderate" || recommendation.includes("Controlled")) {
    return "Tomorrow looks better for controlled work than for another hard day.";
  }
  return "Tomorrow looks better for easy work and recovery support.";
}

function tomorrowWindowLabel(intensityPermission, recommendation) {
  if (intensityPermission === "vo2" || recommendation.includes("Quality")) {
    return "Best fit for tomorrow: quality if today's session stays under control.";
  }
  if (recommendation.includes("Strength")) {
    return "Best fit for tomorrow: strength-led work.";
  }
  if (intensityPermission === "moderate" || recommendation.includes("Controlled")) {
    return "Best fit for tomorrow: controlled aerobic or steady work.";
  }
  return "Best fit for tomorrow: easy or recovery work.";
}

function outlookCapacityLabel(decision) {
  if (!decision) {
    return "Stable";
  }
  if (decision.primaryRecommendation === "Recovery day" || decision.primaryRecommendation === "Avoid intensity") {
    return decision.loadTolerance === "Low" ? "Low capacity" : "Recovery likely";
  }
  if (decision.recoveryStatus === "Poor") {
    return decision.loadTolerance === "Low" ? "Low capacity" : "Fatigued";
  }
  if (decision.recoveryStatus === "Borderline") {
    return decision.loadTolerance === "Low" ? "Low capacity" : "Borderline";
  }
  return "Stable";
}

function advanceSimulationState(state, sessionProfile) {
  const nextRecoveryScore = clampNumber(
    safeNumber(state.recoveryScore) - sessionProfile.fatigueCost + RECOVERY_REGEN,
    MIN_RECOVERY_SCORE,
    MAX_RECOVERY_SCORE,
    -0.05,
  );
  const passiveLoadDecay = state.loadRatio === null
    ? LOAD_DECAY
    : LOAD_DECAY + Math.max(0, state.loadRatio - 1.0) * 0.12;
  const loadImpactDelta = sessionProfile.loadImpact * LOAD_IMPACT_SCALE;
  const nextLoadRatio = state.loadRatio === null
    ? null
    : clampNumber(
        state.loadRatio + loadImpactDelta - passiveLoadDecay,
        MIN_LOAD_RATIO,
        MAX_LOAD_RATIO,
        state.loadRatio,
      );
  const nextQualityFlags = [Boolean(sessionProfile.qualityFlag), ...state.recentQualityFlags].slice(0, 7);
  const nextSessionCategories = [sessionProfile.category, ...state.recentSessionCategories].slice(0, 7);
  const nextConditionScore = clampNumber(
    (safeNumber(state.conditionScore) ?? safeNumber(state.recoveryScore) ?? 0) * 0.45 + nextRecoveryScore * 0.55,
    -1,
    1,
    nextRecoveryScore,
  );

  return {
    ...state,
    recoveryScore: nextRecoveryScore,
    loadRatio: nextLoadRatio,
    hardSessionsLast3d: countQualityFlags(nextQualityFlags.slice(0, 3)),
    hardSessionsLast7d: countQualityFlags(nextQualityFlags),
    yesterdaySessionType: sessionProfile.category,
    lastSessionType: sessionProfile.category,
    lastSessionIntensity: sessionProfile.category,
    recentSessionCategories: nextSessionCategories,
    recentQualityFlags: nextQualityFlags,
    readiness: deriveReadiness(nextRecoveryScore, state.readiness),
    conditionScore: nextConditionScore,
    comparisons: deriveComparisonsFromCondition(nextConditionScore, state.comparisons),
    restingHrDeltaBpm: deriveRestingHrDeltaBpmFromCondition(nextConditionScore),
    veryHighYesterdayLoad: sessionProfile.category === "vo2" || sessionProfile.loadImpact >= 0.75,
  };
}

function deriveComparisonsFromCondition(conditionScore, previousComparisons = {}) {
  const bounded = clampNumber(conditionScore, -1, 1, 0);
  return {
    hrvDeltaPct: roundTo(blendMetric(previousComparisons?.hrvDeltaPct, bounded * 18), 1),
    sleepDeltaPct: roundTo(blendMetric(previousComparisons?.sleepDeltaPct, bounded * 12), 1),
    respirationDeltaPct: roundTo(blendMetric(previousComparisons?.respirationDeltaPct, bounded * -6), 1),
    restingHrDeltaPct: roundTo(blendMetric(previousComparisons?.restingHrDeltaPct, bounded * -7), 1),
  };
}

function deriveReadiness(recoveryScore, previousReadiness) {
  const baseReadiness = previousReadiness === null ? 65 : Number(previousReadiness);
  const derived = 62 + recoveryScore * 28;
  return clampInteger(Math.round(baseReadiness * 0.4 + derived * 0.6), 20, 95, 65);
}

function deriveConditionScore({ recoveryScore, comparisons, restingHrDeltaBpm }) {
  const signals = [];
  if (safeNumber(comparisons?.hrvDeltaPct) !== null) {
    signals.push(clampNumber(comparisons.hrvDeltaPct / 20, -1, 1, 0));
  }
  if (safeNumber(comparisons?.sleepDeltaPct) !== null) {
    signals.push(clampNumber(comparisons.sleepDeltaPct / 20, -1, 1, 0));
  }
  if (safeNumber(comparisons?.respirationDeltaPct) !== null) {
    signals.push(clampNumber(comparisons.respirationDeltaPct / -8, -1, 1, 0));
  }
  if (safeNumber(restingHrDeltaBpm) !== null) {
    signals.push(clampNumber(restingHrDeltaBpm / -4, -1, 1, 0));
  }
  if (!signals.length) {
    return clampNumber(recoveryScore, -1, 1, 0);
  }
  return roundTo(signals.reduce((sum, value) => sum + value, 0) / signals.length, 2);
}

function deriveRestingHrDeltaBpm(currentMetrics, baseline) {
  const currentValue = safeNumber(currentMetrics?.restingHr);
  const baselineValue = safeNumber(baseline?.restingHr);
  if (currentValue === null || baselineValue === null) {
    return null;
  }
  return roundTo(currentValue - baselineValue, 1);
}

function deriveRestingHrDeltaBpmFromCondition(conditionScore) {
  return roundTo(clampNumber(conditionScore, -1, 1, 0) * -2.6, 1);
}

function seedRecentSessionCategories(currentLoad) {
  const yesterdayType = sessionCategoryForType(currentLoad?.yesterdaySessionType) || currentLoad?.yesterdaySessionType || "easy";
  const hard3 = clampInteger(currentLoad?.hardSessionsLast3d, 0, 3, 0);
  const hard7 = clampInteger(currentLoad?.hardSessionsLast7d, hard3, 7, hard3);
  const categories = new Array(7).fill("easy");
  const fillOrder = [0, 2, 1, 4, 6, 5, 3];

  categories[0] = yesterdayType;
  let assigned = isQualityCategory(categories[0]) ? 1 : 0;

  for (const index of fillOrder) {
    if (assigned >= hard7) {
      break;
    }
    if (index === 0) {
      continue;
    }
    categories[index] = "threshold";
    assigned += 1;
  }

  if (!isQualityCategory(categories[0]) && hard3 > 0) {
    categories[1] = "threshold";
  }

  return categories;
}

function seedRecentQualityFlags(currentLoad) {
  return seedRecentSessionCategories(currentLoad).map((category) => isQualityCategory(category));
}

function categoryFromPrimaryRecommendation(primaryRecommendation, intensityPermission) {
  if (["Recovery day", "Avoid intensity"].includes(primaryRecommendation)) {
    return "recovery";
  }
  if (primaryRecommendation === "VO2max OK" || intensityPermission === "vo2") {
    return "vo2";
  }
  if (primaryRecommendation === "Threshold OK" || intensityPermission === "threshold") {
    return "threshold";
  }
  if (primaryRecommendation === "Strength OK") {
    return "heavy_strength";
  }
  if (primaryRecommendation === "Moderate only" || intensityPermission === "moderate") {
    return "moderate";
  }
  return "easy";
}

function categoryDefaults(category) {
  return forecastProfileForSessionType(category) || {
    fatigueCost: 0.2,
    loadImpact: 0.2,
    qualityFlag: false,
  };
}

function summarizeState(state) {
  return {
    recoveryScore: roundTo(state.recoveryScore, 2),
    loadRatio: state.loadRatio === null ? null : roundTo(state.loadRatio, 2),
    hardSessionsLast3d: state.hardSessionsLast3d,
    hardSessionsLast7d: state.hardSessionsLast7d,
    lastSessionType: state.lastSessionType,
    readiness: state.readiness,
    conditionScore: state.conditionScore,
  };
}

function forecastDayLabel(anchorDate, offset) {
  if (offset === 1) {
    return "Tomorrow";
  }
  const date = addDays(anchorDate, offset);
  if (!date) {
    return `Day +${offset}`;
  }
  const parsed = new Date(`${date}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return `Day +${offset}`;
  }
  return parsed.toLocaleDateString("en-US", { weekday: "short" });
}

function addDays(dateValue, daysToAdd) {
  if (!dateValue) {
    return null;
  }
  const parsed = new Date(`${dateValue}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  parsed.setDate(parsed.getDate() + daysToAdd);
  return parsed.toISOString().slice(0, 10);
}

function applyIntensityTrace(rawIntensity, override) {
  return {
    ...rawIntensity,
    ...override,
    trace: [...(rawIntensity.trace || []), ...(override.trace || [])],
  };
}

function unavailableOutlook(reason) {
  return {
    available: false,
    reason,
    days: [],
    tomorrowImpact: {
      headline: "Outlook Unavailable",
      text: "Outlook unavailable for the selected day.",
      predictedScore: null,
      tone: "neutral",
    },
    trace: null,
  };
}

function blendMetric(previousValue, derivedValue) {
  const previous = safeNumber(previousValue);
  if (previous === null) {
    return derivedValue;
  }
  return previous * 0.35 + derivedValue * 0.65;
}

function countQualityFlags(flags) {
  return flags.filter(Boolean).length;
}

function clampInteger(value, min, max, fallback) {
  if (!Number.isFinite(Number(value))) {
    return fallback;
  }
  return Math.max(min, Math.min(max, Math.round(Number(value))));
}

function clampNumber(value, min, max, fallback) {
  const numeric = safeNumber(value);
  if (numeric === null) {
    return fallback;
  }
  return Math.max(min, Math.min(max, numeric));
}

function roundTo(value, digits) {
  const factor = 10 ** digits;
  return Math.round(Number(value) * factor) / factor;
}

function safeNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}
