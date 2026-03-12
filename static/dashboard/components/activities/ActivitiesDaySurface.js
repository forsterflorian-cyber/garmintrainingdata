import { el, formatNumber, safeHtml, safeText } from "../../lib/formatters.js";
import { compareCompletedSessionToDecision } from "../../lib/planDecisionUtils.js";
import { renderBaselineComparisonCard } from "../metrics/BaselineComparisonCard.js";

const ACTIVITIES_EMPTY_COPY = "No activities recorded for the selected day.";
const ACTIVITIES_NO_HISTORY_COPY = "No synced history is available yet.";
const RECOMMENDATION_EMPTY_COPY = "No recommendation data is available for the selected day.";
const RECOMMENDATION_WHY_EMPTY_COPY = "No decision context is available for the selected day.";
const OPTIONS_EMPTY_COPY = "No session options are available for the selected day.";

export function renderActivitiesDaySurface(
  payload = {},
  { availableDays = [], selectedDate = null, onSelectDay = null, mode = "hybrid", todayDate = null } = {},
) {
  const resolvedDate = firstDate(selectedDate, payload?.date);
  const effectiveSelectedDate = renderDaySelector(availableDays, resolvedDate, onSelectDay, todayDate);
  renderSelectionMeta(availableDays, effectiveSelectedDate);
  renderActualActivities(payload, effectiveSelectedDate);
  renderRecommendation(payload, effectiveSelectedDate, mode);
  renderBaseline(payload, effectiveSelectedDate);
}

function renderDaySelector(availableDays, selectedDate, onSelectDay, todayDate) {
  const target = el("activitiesDaySelect");
  const previousButton = el("activitiesPrevDayBtn");
  const nextButton = el("activitiesNextDayBtn");
  if (!target) {
    return selectedDate;
  }

  const normalizedDays = buildDayOptions(availableDays, todayDate);
  if (!normalizedDays.length) {
    target.disabled = true;
    target.innerHTML = '<option value="">No days available</option>';
    target.value = "";
    target.onchange = null;
    syncDayNavigationButtons(previousButton, nextButton);
    return selectedDate;
  }

  const resolvedDate = normalizedDays.some((day) => day.date === selectedDate)
    ? selectedDate
    : normalizedDays[0].date;
  const selectedIndex = normalizedDays.findIndex((day) => day.date === resolvedDate);

  target.disabled = false;
  target.innerHTML = normalizedDays.map((day) => `
    <option value="${safeHtml(day.date)}">${safeHtml(day.label)}</option>
  `).join("");
  target.value = resolvedDate;
  target.onchange = (event) => {
    const nextDate = event?.target?.value;
    if (typeof onSelectDay === "function" && nextDate) {
      onSelectDay(nextDate);
    }
  };

  syncDayNavigationButtons(
    previousButton,
    nextButton,
    normalizedDays[selectedIndex + 1]?.date || null,
    normalizedDays[selectedIndex - 1]?.date || null,
    onSelectDay,
  );

  return resolvedDate;
}

function renderSelectionMeta(availableDays, selectedDate) {
  const target = el("activitiesSelectionMeta");
  if (!target) {
    return;
  }

  const normalizedDays = sanitizeDayOptions(availableDays);
  if (!normalizedDays.length) {
    target.textContent = ACTIVITIES_NO_HISTORY_COPY;
    return;
  }

  target.textContent = selectedDate
    ? `Inspecting ${selectedDate}. Newest days stay at the top.`
    : "Select a day to inspect historical activity, recommendation, and baseline data.";
}

function renderActualActivities(payload, selectedDate) {
  const headline = el("activitiesActualHeadline");
  const summary = el("activitiesActualSummary");
  const list = el("activitiesActualList");

  if (!headline || !summary || !list) {
    return;
  }

  const detail = payload?.detail || {};
  const decision = payload?.decision || {};
  const activities = sanitizedActivities(detail.activities);
  const resolvedDate = firstDate(selectedDate, detail?.activeDate, payload?.date);

  headline.textContent = resolvedDate ? `Activities On ${resolvedDate}` : "Activities On -";

  if (!resolvedDate) {
    summary.innerHTML = "";
    list.innerHTML = `<div class="muted-copy">${ACTIVITIES_NO_HISTORY_COPY}</div>`;
    return;
  }

  const dominantDaySport = dominantSportTag(activities);
  const dayComparison = detail?.sessionType
    ? compareCompletedSessionToDecision(detail.sessionType, decision, { sportTag: dominantDaySport })
    : null;
  const activitiesWithComparison = activities.map((activity) => ({
    activity,
    comparison: activity?.sessionType
      ? compareCompletedSessionToDecision(activity.sessionType, decision, { sportTag: activity.sport_tag })
      : null,
  }));

  const totalDuration = summarizeMetric(activities, "duration_min");
  const totalLoad = summarizeMetric(activities, "training_load");
  summary.innerHTML = `
    <article class="activity-day-card">
      <div class="relative-head">
        <div>
          <div class="relative-title">Selected Day Context</div>
          <div class="muted-copy">${safeHtml(safeText(decision.primaryRecommendation, "No recommendation"))}</div>
        </div>
        ${comparisonBadge(dayComparison)}
      </div>
      <div class="activity-chips">
        <span class="chip">${safeHtml(`${activities.length} activit${activities.length === 1 ? "y" : "ies"}`)}</span>
        <span class="chip">Duration ${safeHtml(metricSummaryText(totalDuration, 0, "min"))}</span>
        <span class="chip">Load ${safeHtml(metricSummaryText(totalLoad, 0))}</span>
      </div>
      ${dayComparison?.detail ? `<p class="muted-copy activity-comparison-detail">${safeHtml(dayComparison.detail)}</p>` : ""}
    </article>
  `;

  if (!activities.length) {
    list.innerHTML = `<div class="muted-copy">${ACTIVITIES_EMPTY_COPY}</div>`;
    return;
  }

  list.innerHTML = activitiesWithComparison.map(({ activity, comparison }) => renderActivityCard(activity, comparison)).join("");
}

function renderRecommendation(payload, selectedDate, mode) {
  const headline = el("activitiesRecommendationHeadline");
  const summary = el("activitiesRecommendationSummary");
  const whyTarget = el("activitiesRecommendationWhy");
  const optionsTarget = el("activitiesRecommendationOptions");

  if (!headline || !summary || !whyTarget || !optionsTarget) {
    return;
  }

  const decision = payload?.decision || {};
  const bestOptions = Array.isArray(decision.bestOptions) ? decision.bestOptions : [];
  const why = Array.isArray(decision.why)
    ? decision.why.filter((line) => typeof line === "string" && line.trim())
    : [];

  headline.textContent = selectedDate ? `Recommendation For ${selectedDate}` : "Recommendation For -";

  if (!selectedDate) {
    summary.innerHTML = `<div class="muted-copy">${RECOMMENDATION_EMPTY_COPY}</div>`;
    whyTarget.innerHTML = "";
    optionsTarget.innerHTML = "";
    return;
  }

  if (!decision.primaryRecommendation && !decision.summaryText && !why.length && !bestOptions.length) {
    summary.innerHTML = `<div class="muted-copy">${RECOMMENDATION_EMPTY_COPY}</div>`;
    whyTarget.innerHTML = `<div class="muted-copy">${RECOMMENDATION_WHY_EMPTY_COPY}</div>`;
    optionsTarget.innerHTML = "";
    return;
  }

  summary.innerHTML = `
    <article class="activity-day-card">
      <div class="relative-head">
        <div>
          <div class="relative-title">${safeHtml(modeLabel(mode))} recommendation</div>
          <div class="relative-value">${safeHtml(safeText(decision.primaryRecommendation, "No recommendation"))}</div>
        </div>
        <div class="activity-card-meta">
          <span class="activity-comparison-badge" data-tone="neutral">Load ${safeHtml(safeText(decision.loadTolerance, "Unknown"))}</span>
        </div>
      </div>
      <p class="muted-copy activity-comparison-detail">${safeHtml(safeText(decision.summaryText, RECOMMENDATION_EMPTY_COPY))}</p>
    </article>
  `;

  whyTarget.innerHTML = why.length
    ? why.map((line) => `
      <article class="why-item">
        <span class="why-bullet"></span>
        <span>${safeHtml(line)}</span>
      </article>
    `).join("")
    : `<div class="muted-copy">${RECOMMENDATION_WHY_EMPTY_COPY}</div>`;

  optionsTarget.innerHTML = bestOptions.length
    ? bestOptions.map((option, index) => `
      <article class="unit-card">
        <p class="eyebrow">Option ${index + 1}</p>
        <div class="relative-title">${safeHtml(safeText(option?.label, "Plan option"))}</div>
        <p class="muted-copy activity-comparison-detail">${safeHtml(safeText(option?.details, "No option details available."))}</p>
      </article>
    `).join("")
    : `<div class="muted-copy">${OPTIONS_EMPTY_COPY}</div>`;
}

function renderBaseline(payload, selectedDate) {
  const headline = el("activitiesBaselineHeadline");
  const reference = el("activitiesBaselineReference");

  if (headline) {
    headline.textContent = selectedDate ? `${selectedDate} Vs Baseline` : "Selected Day Vs Baseline";
  }

  if (reference) {
    if (!selectedDate) {
      reference.textContent = "Reference window follows the selected range.";
    } else {
      const sampleDays = Number(payload?.reference?.baselineSampleDays || 0);
      const baselineDays = safeNumericValue(payload?.reference?.baselineDays);
      const baselineSource = typeof payload?.reference?.baselineSource === "string" ? payload.reference.baselineSource : null;
      if (baselineSource === "rolling" && baselineDays !== null) {
        reference.textContent = `Rolling ${formatNumber(baselineDays, 0)}-day reference ending before the selected day. ${sampleDays ? `Samples used: ${sampleDays} days.` : ""}`.trim();
      } else if (baselineDays !== null) {
        reference.textContent = `Stored Garmin baseline shown because the ${formatNumber(baselineDays, 0)}-day range does not yet have enough prior samples.`;
      } else {
        reference.textContent = "Reference window follows the selected range.";
      }
    }
  }

  renderBaselineComparisonCard(payload?.baselineBars || [], {
    targetId: "activitiesBaselineMetricList",
    emptyCopy: "No baseline comparison available for the selected day.",
  });
}

function sanitizeDayOptions(availableDays) {
  if (!Array.isArray(availableDays)) {
    return [];
  }
  return Array.from(new Set(availableDays
    .map((day) => {
      if (typeof day === "string") {
        return day.trim();
      }
      if (typeof day?.date === "string") {
        return day.date.trim();
      }
      return "";
    })
    .filter(Boolean)))
    .sort((left, right) => right.localeCompare(left));
}

function buildDayOptions(availableDays, todayDate) {
  return sanitizeDayOptions(availableDays).map((date) => ({
    date,
    label: labelForDay(date, todayDate),
  }));
}

function labelForDay(date, todayDate) {
  if (!todayDate) {
    return date;
  }
  if (date === todayDate) {
    return "Today";
  }
  if (date === shiftIsoDate(todayDate, -1)) {
    return "Yesterday";
  }
  return date;
}

function shiftIsoDate(date, days) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(date || "").trim());
  if (!match) {
    return null;
  }
  const shiftedDate = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days));
  return shiftedDate.toISOString().slice(0, 10);
}

function syncDayNavigationButtons(previousButton, nextButton, previousDate = null, nextDate = null, onSelectDay = null) {
  if (previousButton) {
    previousButton.disabled = !previousDate;
    previousButton.onclick = previousDate && typeof onSelectDay === "function"
      ? () => onSelectDay(previousDate)
      : null;
  }

  if (nextButton) {
    nextButton.disabled = !nextDate;
    nextButton.onclick = nextDate && typeof onSelectDay === "function"
      ? () => onSelectDay(nextDate)
      : null;
  }
}

function renderActivityCard(activity, comparison) {
  const chips = buildActivityChips(activity);
  return `
    <article class="activity-card">
      <div class="relative-head">
        <div>
          <div class="relative-title">${safeHtml(activityTitle(activity))}</div>
          <div class="muted-copy">${safeHtml(activityMetaLine(activity))}</div>
        </div>
        <div class="activity-card-meta">
          ${comparisonBadge(comparison)}
          <div class="relative-value">${activityDurationText(activity)}</div>
        </div>
      </div>
      <div class="activity-chips">
        ${chips.length ? chips.map((chip) => `<span class="chip">${safeHtml(chip)}</span>`).join("") : '<span class="chip">Partial Garmin metadata</span>'}
      </div>
      ${comparison?.detail ? `<p class="muted-copy activity-comparison-detail">${safeHtml(comparison.detail)}</p>` : ""}
    </article>
  `;
}

function dominantSportTag(activities) {
  const totals = new Map();
  activities.forEach((activity) => {
    const sportTag = safeText(activity?.sport_tag, "");
    if (!sportTag) {
      return;
    }
    const loadValue = safeNumericValue(activity?.training_load) || 0;
    const durationValue = safeNumericValue(activity?.duration_min) || 0;
    const weight = loadValue > 0 ? loadValue : durationValue;
    totals.set(sportTag, (totals.get(sportTag) || 0) + weight);
  });

  let winner = null;
  let winnerScore = -1;
  totals.forEach((score, sportTag) => {
    if (score > winnerScore) {
      winner = sportTag;
      winnerScore = score;
    }
  });
  return winner;
}

function comparisonBadge(comparison) {
  if (!comparison?.label) {
    return "";
  }
  return `<span class="activity-comparison-badge" data-tone="${safeHtml(comparison.tone || "neutral")}">${safeHtml(comparison.label)}</span>`;
}

function summarizeMetric(activities, key) {
  let total = 0;
  let hasValue = false;
  activities.forEach((activity) => {
    const value = safeNumericValue(activity?.[key]);
    if (value === null) {
      return;
    }
    total += value;
    hasValue = true;
  });
  return { total, hasValue };
}

function metricSummaryText(summary, digits = 0, suffix = "") {
  if (!summary?.hasValue) {
    return "-";
  }
  const rendered = formatNumber(summary.total, digits);
  return suffix ? `${rendered} ${suffix}` : rendered;
}

function buildActivityChips(activity) {
  const chips = [];
  pushActivityChip(chips, "Avg HR", activity?.avg_hr, 0);
  pushActivityChip(chips, "Max HR", activity?.max_hr, 0);
  const aerobicTe = safeNumericValue(activity?.aerobic_te);
  const anaerobicTe = safeNumericValue(activity?.anaerobic_te);
  if (aerobicTe !== null || anaerobicTe !== null) {
    chips.push(`TE ${formatNumber(aerobicTe, 1)} / ${formatNumber(anaerobicTe, 1)}`);
  }
  pushActivityChip(chips, "Load", activity?.training_load, 1);
  if (typeof activity?.pace_min_per_km === "string" && activity.pace_min_per_km.trim()) {
    chips.push(`Pace ${activity.pace_min_per_km.trim()} /km`);
  } else {
    pushActivityChip(chips, "Distance", activity?.distance_km, 1, "km");
  }
  return chips;
}

function pushActivityChip(chips, label, value, digits = 0, suffix = "") {
  const numericValue = safeNumericValue(value);
  if (numericValue === null) {
    return;
  }
  const rendered = suffix ? `${formatNumber(numericValue, digits)} ${suffix}` : formatNumber(numericValue, digits);
  chips.push(`${label} ${rendered}`);
}

function activityTitle(activity) {
  if (typeof activity?.name === "string" && activity.name.trim()) {
    return activity.name.trim();
  }
  if (typeof activity?.type_key === "string" && activity.type_key.trim()) {
    return activity.type_key.trim();
  }
  return "Activity";
}

function activityMetaLine(activity) {
  const typeText = safeText(activity?.type_key, "Unknown type");
  const timeText = firstNonEmptyText(activity?.start_local, activity?.date_local, "Time unavailable");
  return `${typeText} | ${timeText}`;
}

function activityDurationText(activity) {
  const duration = safeNumericValue(activity?.duration_min);
  return duration === null ? "-" : `${formatNumber(duration, 0)} min`;
}

function sanitizedActivities(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((activity) => activity && typeof activity === "object");
}

function firstNonEmptyText(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function safeNumericValue(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function firstDate(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function modeLabel(mode) {
  return {
    hybrid: "Hybrid",
    run: "Run focus",
    bike: "Bike focus",
    strength: "Strength focus",
  }[mode] || "Selected";
}
