/**
 * Advanced Metrics Card Component
 * Zeigt Power, Pace und HR Metriken für Aktivitäten an
 */

import { el, formatNumber, safeHtml, safeText } from "../../lib/formatters.js";

/**
 * Rendert erweiterte Metriken für eine Aktivität
 */
export function renderAdvancedMetricsCard(activity, userProfile) {
  const container = el("advancedMetricsCard");
  if (!container) {
    return;
  }

  // Prüfe ob Metriken verfügbar sind
  const hasPowerMetrics = activity.power_metrics && userProfile?.ftp;
  const hasPaceMetrics = activity.pace_metrics && userProfile?.critical_pace;
  const hasHrMetrics = activity.hr_metrics && userProfile?.max_hr;

  if (!hasPowerMetrics && !hasPaceMetrics && !hasHrMetrics) {
    container.innerHTML = `
      <div class="advanced-metrics-card advanced-metrics-card--empty">
        <div class="advanced-metrics-title">Advanced Metrics</div>
        <div class="advanced-metrics-value muted-copy">No advanced metrics available.</div>
        <div class="advanced-metrics-hint">Set up your profile (FTP, Critical Pace, Max HR) to see detailed metrics.</div>
      </div>
    `;
    return;
  }

  let html = `<div class="advanced-metrics-card">`;
  html += `<div class="advanced-metrics-title">Advanced Metrics</div>`;
  html += `<div class="advanced-metrics-grid">`;

  // Power Metrics (Cycling)
  if (hasPowerMetrics) {
    const power = activity.power_metrics;
    html += `
      <div class="metrics-section">
        <div class="metrics-section-title">
          <span class="metrics-icon">⚡</span>
          Power Analysis
        </div>
        <div class="metrics-grid">
          ${renderMetricRow("FTP", `${power.ftp}W`, "Functional Threshold Power")}
          ${renderMetricRow("IF", formatNumber(power.intensity_factor, 2), "Intensity Factor")}
          ${renderMetricRow("TSS", formatNumber(power.tss, 0), "Training Stress Score")}
          ${renderMetricRow("VI", formatNumber(power.variability_index, 2), "Variability Index")}
          ${power.power_to_weight ? renderMetricRow("W/kg", formatNumber(power.power_to_weight, 2), "Power to Weight") : ""}
        </div>
        ${renderZoneDistribution(power.zone_distribution, "Power Zones")}
      </div>
    `;
  }

  // Pace Metrics (Running)
  if (hasPaceMetrics) {
    const pace = activity.pace_metrics;
    html += `
      <div class="metrics-section">
        <div class="metrics-section-title">
          <span class="metrics-icon">🏃</span>
          Pace Analysis
        </div>
        <div class="metrics-grid">
          ${renderMetricRow("CP", `${formatNumber(pace.critical_pace, 2)} min/km`, "Critical Pace")}
          ${renderMetricRow("Avg", `${formatNumber(pace.avg_pace, 2)} min/km`, "Average Pace")}
          ${renderMetricRow("Best", `${formatNumber(pace.best_pace, 2)} min/km`, "Best Pace")}
          ${pace.trimp ? renderMetricRow("TRIMP", formatNumber(pace.trimp, 0), "Training Impulse") : ""}
          ${pace.pace_variability ? renderMetricRow("CV", formatNumber(pace.pace_variability, 3), "Pace Variability") : ""}
        </div>
        ${renderZoneDistribution(pace.zone_distribution, "Pace Zones")}
        ${pace.splits && pace.splits.length > 0 ? renderSplits(pace.splits) : ""}
      </div>
    `;
  }

  // HR Metrics (alle Sportarten)
  if (hasHrMetrics) {
    const hr = activity.hr_metrics;
    html += `
      <div class="metrics-section">
        <div class="metrics-section-title">
          <span class="metrics-icon">❤️</span>
          Heart Rate Analysis
        </div>
        <div class="metrics-grid">
          ${renderMetricRow("Avg HR", `${hr.avg_hr} bpm`, "Average Heart Rate")}
          ${renderMetricRow("Peak HR", `${hr.peak_hr} bpm`, "Peak Heart Rate")}
          ${hr.hrr_1min ? renderMetricRow("HRR", `${hr.hrr_1min} bpm`, "Heart Rate Recovery") : ""}
          ${hr.hr_training_load ? renderMetricRow("Load", formatNumber(hr.hr_training_load, 0), "Training Load") : ""}
          ${hr.efficiency_factor ? renderMetricRow("EF", formatNumber(hr.efficiency_factor, 2), "Efficiency Factor") : ""}
          ${hr.decoupling !== null ? renderMetricRow("Dec", `${formatNumber(hr.decoupling, 1)}%`, "Decoupling") : ""}
        </div>
        ${renderZoneDistribution(hr.zone_distribution, "HR Zones")}
        ${hr.time_in_zones ? renderTimeInZones(hr.time_in_zones) : ""}
      </div>
    `;
  }

  html += `</div>`;
  html += `</div>`;

  container.innerHTML = html;
}

/**
 * Rendert eine einzelne Metrik-Zeile
 */
function renderMetricRow(label, value, description) {
  return `
    <div class="metric-row" title="${safeHtml(description)}">
      <span class="metric-label">${safeHtml(label)}</span>
      <span class="metric-value">${safeHtml(value)}</span>
    </div>
  `;
}

/**
 * Rendert Zonen-Verteilung
 */
function renderZoneDistribution(distribution, title) {
  if (!distribution) {
    return "";
  }

  const zones = Object.entries(distribution)
    .filter(([_, pct]) => pct > 0)
    .sort((a, b) => b[1] - a[1]);

  if (zones.length === 0) {
    return "";
  }

  let html = `<div class="zone-distribution">`;
  html += `<div class="zone-distribution-title">${safeHtml(title)}</div>`;
  html += `<div class="zone-bars">`;

  for (const [zone, pct] of zones) {
    const color = getZoneColor(zone);
    html += `
      <div class="zone-bar" style="width: ${pct}%; background-color: ${color};" title="${safeHtml(zone)}: ${formatNumber(pct, 1)}%">
        <span class="zone-label">${safeHtml(zone.split(":")[0])}</span>
        <span class="zone-pct">${formatNumber(pct, 0)}%</span>
      </div>
    `;
  }

  html += `</div>`;
  html += `</div>`;
  return html;
}

/**
 * Rendert Splits
 */
function renderSplits(splits) {
  if (!splits || splits.length === 0) {
    return "";
  }

  let html = `<div class="splits-section">`;
  html += `<div class="splits-title">Kilometer Splits</div>`;
  html += `<div class="splits-list">`;

  for (const split of splits.slice(0, 10)) {  // Max 10 Splits anzeigen
    const color = getZoneColor(split.zone);
    html += `
      <div class="split-row">
        <span class="split-km">Km ${split.km}</span>
        <span class="split-pace" style="color: ${color}">${formatNumber(split.pace, 2)} min/km</span>
        <span class="split-zone">${safeHtml(split.zone.split(":")[0])}</span>
      </div>
    `;
  }

  html += `</div>`;
  html += `</div>`;
  return html;
}

/**
 * Rendert Time in Zones
 */
function renderTimeInZones(timeInZones) {
  if (!timeInZones) {
    return "";
  }

  const zones = Object.entries(timeInZones)
    .filter(([_, minutes]) => minutes > 0)
    .sort((a, b) => b[1] - a[1]);

  if (zones.length === 0) {
    return "";
  }

  let html = `<div class="time-in-zones">`;
  html += `<div class="time-in-zones-title">Time in Zones</div>`;
  html += `<div class="time-in-zones-list">`;

  for (const [zone, minutes] of zones) {
    const color = getZoneColor(zone);
    html += `
      <div class="time-zone-row">
        <span class="time-zone-name" style="color: ${color}">${safeHtml(zone.split(":")[0])}</span>
        <span class="time-zone-minutes">${formatNumber(minutes, 0)} min</span>
      </div>
    `;
  }

  html += `</div>`;
  html += `</div>`;
  return html;
}

/**
 * Gibt Farbe für Zone zurück
 */
function getZoneColor(zone) {
  const zoneLower = zone.toLowerCase();
  
  if (zoneLower.includes("recovery") || zoneLower.includes("z1")) {
    return "#22c55e";  // Grün
  }
  if (zoneLower.includes("easy") || zoneLower.includes("z2") || zoneLower.includes("endurance")) {
    return "#3b82f6";  // Blau
  }
  if (zoneLower.includes("moderate") || zoneLower.includes("z3") || zoneLower.includes("tempo")) {
    return "#eab308";  // Gelb
  }
  if (zoneLower.includes("threshold") || zoneLower.includes("z4")) {
    return "#f97316";  // Orange
  }
  if (zoneLower.includes("vo2") || zoneLower.includes("z5")) {
    return "#ef4444";  // Rot
  }
  if (zoneLower.includes("anaerobic") || zoneLower.includes("z6")) {
    return "#dc2626";  // Dunkelrot
  }
  if (zoneLower.includes("sprint") || zoneLower.includes("z7")) {
    return "#991b1b";  // Sehr dunkelrot
  }
  
  return "#6b7280";  // Grau als Fallback
}

/**
 * Rendert erweiterte Metriken Zusammenfassung
 */
export function renderAdvancedMetricsSummary(activities, userProfile) {
  const container = el("advancedMetricsSummary");
  if (!container) {
    return;
  }

  if (!activities || activities.length === 0) {
    container.innerHTML = "";
    return;
  }

  // Aggregiere Metriken über alle Aktivitäten
  let totalTss = 0;
  let totalTrimp = 0;
  let totalHrLoad = 0;
  let activitiesWithPower = 0;
  let activitiesWithPace = 0;
  let activitiesWithHr = 0;

  for (const activity of activities) {
    if (activity.power_metrics) {
      totalTss += activity.power_metrics.tss || 0;
      activitiesWithPower++;
    }
    if (activity.pace_metrics) {
      totalTrimp += activity.pace_metrics.trimp || 0;
      activitiesWithPace++;
    }
    if (activity.hr_metrics) {
      totalHrLoad += activity.hr_metrics.hr_training_load || 0;
      activitiesWithHr++;
    }
  }

  if (activitiesWithPower === 0 && activitiesWithPace === 0 && activitiesWithHr === 0) {
    container.innerHTML = "";
    return;
  }

  let html = `<div class="advanced-metrics-summary">`;
  html += `<div class="advanced-metrics-summary-title">Period Metrics</div>`;
  html += `<div class="advanced-metrics-summary-grid">`;

  if (activitiesWithPower > 0) {
    html += `
      <div class="summary-metric">
        <span class="summary-metric-label">Total TSS</span>
        <span class="summary-metric-value">${formatNumber(totalTss, 0)}</span>
        <span class="summary-metric-count">${activitiesWithPower} activities</span>
      </div>
    `;
  }

  if (activitiesWithPace > 0) {
    html += `
      <div class="summary-metric">
        <span class="summary-metric-label">Total TRIMP</span>
        <span class="summary-metric-value">${formatNumber(totalTrimp, 0)}</span>
        <span class="summary-metric-count">${activitiesWithPace} activities</span>
      </div>
    `;
  }

  if (activitiesWithHr > 0) {
    html += `
      <div class="summary-metric">
        <span class="summary-metric-label">Total HR Load</span>
        <span class="summary-metric-value">${formatNumber(totalHrLoad, 0)}</span>
        <span class="summary-metric-count">${activitiesWithHr} activities</span>
      </div>
    `;
  }

  html += `</div>`;
  html += `</div>`;

  container.innerHTML = html;
}