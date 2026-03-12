import { el, formatNumber, safeHtml, safeText } from "../../lib/formatters.js";
import { compareCompletedSessionToDecision } from "../../lib/planDecisionUtils.js";

const HISTORY_EMPTY_COPY = "No history yet. Sync Garmin to build analysis history.";
const ACTIVITIES_EMPTY_COPY = "No activities recorded for the selected history day.";
const ACTIVITIES_NO_HISTORY_COPY = "History selection will appear here after sync.";

export function renderAnalysisHistorySurface(payload = {}, { onSelectDay } = {}) {
  const rows = Array.isArray(payload?.history?.rows) ? payload.history.rows : [];
  const activeDate = typeof payload?.date === "string" && payload.date ? payload.date : null;

  renderUnifiedHistory(rows, activeDate, onSelectDay);
  renderActivities(payload, rows, activeDate);
}

export function renderUnifiedHistory(rows, activeDate, onSelectDay = null) {
  const target = el("historyTable");
  if (!target) {
    return;
  }

  const orderedRows = rows.slice().reverse();
  if (!orderedRows.length) {
    target.innerHTML = `<tr><td colspan="6" class="muted-copy">${safeHtml(HISTORY_EMPTY_COPY)}</td></tr>`;
    return;
  }

  const maxLoad = maxHistoryLoad(rows);
  target.innerHTML = orderedRows.map((row) => renderHistoryRow(row, activeDate, maxLoad)).join("");

  target.querySelectorAll(".history-heat-cell[data-day]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (typeof onSelectDay === "function" && button.dataset.day) {
        onSelectDay(button.dataset.day);
      }
    });
  });

  target.querySelectorAll(".history-row[data-day]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (typeof event.target?.closest === "function" && event.target.closest(".history-heat-cell")) {
        return;
      }
      if (typeof onSelectDay === "function" && row.dataset.day) {
        onSelectDay(row.dataset.day);
      }
    });
  });
}

export function renderActivities(payload = {}, historyRows = [], activeDate = null) {
  const headline = el("activityHeadline");
  const selectionMeta = el("activitySelectionMeta");
  const summary = el("activityDaySummary");
  const list = el("activityList");

  if (!headline || !selectionMeta || !summary || !list) {
    return;
  }

  const detail = payload?.detail || {};
  const activities = sanitizedActivities(detail.activities);
  const selectedDate = activeDate || (typeof detail?.activeDate === "string" ? detail.activeDate : null);

  if (!selectedDate && !historyRows.length) {
    headline.textContent = "Focus Day Activities";
    selectionMeta.textContent = ACTIVITIES_NO_HISTORY_COPY;
    summary.innerHTML = "";
    list.innerHTML = `<div class="muted-copy">${ACTIVITIES_EMPTY_COPY}</div>`;
    return;
  }

  headline.textContent = selectedDate ? `Activities On ${selectedDate}` : "Focus Day Activities";
  selectionMeta.textContent = selectedDate
    ? `Selected in History: ${selectedDate}`
    : "Selected history day unavailable.";

  const dominantDaySport = dominantSportTag(activities);
  const dayComparison = detail?.sessionType
    ? compareCompletedSessionToDecision(detail.sessionType, payload?.decision, { sportTag: dominantDaySport })
    : null;
  const activitiesWithComparison = activities.map((activity) => ({
    activity,
    comparison: activity?.sessionType
      ? compareCompletedSessionToDecision(activity.sessionType, payload?.decision, { sportTag: activity.sport_tag })
      : null,
  }));

  const totalDuration = summarizeMetric(activities, "duration_min");
  const totalLoad = summarizeMetric(activities, "training_load");
  summary.innerHTML = `
    <article class="activity-day-card">
      <div class="relative-head">
        <div>
          <div class="relative-title">Day Context</div>
          <div class="muted-copy">${safeHtml(safeText(payload?.decision?.primaryRecommendation, "No recommendation"))}</div>
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

export function buildHistoryRowMarkup(row, activeDate, maxLoad) {
  return renderHistoryRow(row, activeDate, maxLoad);
}

function renderHistoryRow(row, activeDate, maxLoad) {
  const isActive = row?.date === activeDate;
  const loadStrength = heatStrength(row?.loadDay, maxLoad);
  const recommendation = safeText(row?.primaryRecommendation, "No recommendation");
  return `
    <tr
      class="history-row ${isActive ? "is-active" : ""}"
      data-day="${safeHtml(safeText(row?.date, ""))}"
      aria-selected="${isActive ? "true" : "false"}"
    >
      <td class="history-heat-col">
        <button
          class="history-heat-cell ${isActive ? "is-active" : ""}"
          type="button"
          data-day="${safeHtml(safeText(row?.date, ""))}"
          style="--strength:${loadStrength.toFixed(3)}"
          title="${safeHtml(historyHeatTitle(row))}"
          aria-pressed="${isActive ? "true" : "false"}"
          aria-label="${safeHtml(`Select ${safeText(row?.date, "this day")} from history`)}"
        ></button>
      </td>
      <td>${safeHtml(safeText(row?.date))}</td>
      <td>${formatNumber(row?.readiness, 0)}</td>
      <td>${formatNumber(row?.loadDay, 1)}</td>
      <td>${formatNumber(row?.ratio7to28, 2)}</td>
      <td>${safeHtml(recommendation)}</td>
    </tr>
  `;
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

function maxHistoryLoad(rows) {
  const numericLoads = rows
    .map((row) => safeNumericValue(row?.loadDay))
    .filter((value) => value !== null);
  return numericLoads.length ? Math.max(...numericLoads, 1) : 1;
}

function heatStrength(loadValue, maxLoad) {
  const numericLoad = safeNumericValue(loadValue);
  if (numericLoad === null || maxLoad <= 0) {
    return 0;
  }
  return Math.min(1, numericLoad / maxLoad);
}

function historyHeatTitle(row) {
  const loadText = formatNumber(row?.loadDay, 1);
  const dateText = safeText(row?.date, "Unknown day");
  return `${dateText}: load ${loadText}`;
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
