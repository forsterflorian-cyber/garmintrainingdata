import { safeHtml } from "../../lib/formatters.js";

export function renderRecommendationChips(chips) {
  if (!chips || !chips.length) {
    return '<div class="muted-copy">No decision badges available.</div>';
  }

  return chips.map((chip) => {
    const resolvedChip = resolveChipCopy(chip);
    return `
      <article class="recommendation-chip" data-tone="${safeHtml(resolvedChip.tone)}">
        <div class="recommendation-chip-head">
          <span class="recommendation-chip-dot" aria-hidden="true"></span>
          <span class="recommendation-chip-label">${safeHtml(resolvedChip.label)}</span>
        </div>
        <strong class="recommendation-chip-value">${safeHtml(resolvedChip.value)}</strong>
        <small class="recommendation-chip-detail">${safeHtml(resolvedChip.detail)}</small>
      </article>
    `;
  }).join("");
}

function resolveChipCopy(chip = {}) {
  const label = String(chip.label || "").trim();
  const value = String(chip.value || "").trim();
  const tone = chip.tone || "neutral";

  if (label === "Recovery") {
    return {
      label: "Recovery",
      tone,
      ...(recoveryCopy(value) || { value, detail: "Recovery signal unavailable" }),
    };
  }

  if (label === "Load") {
    return {
      label: "Load",
      tone,
      ...(loadCopy(value) || { value, detail: "Load guidance unavailable" }),
    };
  }

  if (label === "Intensity") {
    return {
      label: "Intensity limit",
      tone,
      ...(intensityCopy(value) || { value, detail: "Intensity guidance unavailable" }),
    };
  }

  if (label === "Confidence") {
    return {
      label: "Confidence",
      tone,
      ...(confidenceCopy(value) || { value, detail: "Use extra judgment today" }),
    };
  }

  return {
    label: label || "Status",
    value: value || "-",
    detail: "No additional guidance",
    tone,
  };
}

function recoveryCopy(value) {
  return {
    Good: { value: "Supportive", detail: "Quality work is supported" },
    Stable: { value: "Steady", detail: "Keep quality controlled" },
    Borderline: { value: "Borderline", detail: "Bias toward moderate work" },
    Poor: { value: "Low", detail: "Keep the day restorative" },
  }[value] || null;
}

function loadCopy(value) {
  return {
    High: { value: "Open", detail: "Load can absorb harder work" },
    Normal: { value: "Controlled", detail: "Current load is manageable" },
    Reduced: { value: "Reduced", detail: "Keep load controlled" },
    Low: { value: "Restricted", detail: "Avoid adding extra load" },
  }[value] || null;
}

function intensityCopy(value) {
  return {
    VO2: { value: "VO2", detail: "High intensity is supported" },
    Threshold: { value: "Threshold", detail: "Quality fits below VO2" },
    Moderate: { value: "Moderate only", detail: "No hard intervals" },
    none: { value: "Recovery only", detail: "Keep intensity out" },
  }[value] || null;
}

function confidenceCopy(value) {
  return {
    High: { value: "High", detail: "Signals are aligned" },
    Medium: { value: "Medium", detail: "Some signals are mixed" },
    Low: { value: "Low", detail: "Use extra judgment today" },
  }[value] || null;
}
