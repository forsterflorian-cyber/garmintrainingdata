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
      label: "Recovery Status",
      tone,
      ...(recoveryCopy(value) || { value, detail: "Recovery status unavailable" }),
    };
  }

  if (label === "Load") {
    return {
      label: "Load Status",
      tone,
      ...(loadCopy(value) || { value, detail: "Load guidance unavailable" }),
    };
  }

  if (label === "Intensity") {
    return {
      label: "Intensity Limit",
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
    Good: { value: "Ready", detail: "Quality work supported" },
    Stable: { value: "Steady", detail: "Controlled quality work fits" },
    Borderline: { value: "Borderline", detail: "Moderate training recommended" },
    Poor: { value: "Low", detail: "Recovery day recommended" },
  }[value] || null;
}

function loadCopy(value) {
  return {
    High: { value: "Open", detail: "Load can support a harder day" },
    Normal: { value: "Balanced", detail: "Current load is under control" },
    Reduced: { value: "Reduced", detail: "Keep load controlled" },
    Low: { value: "Restricted", detail: "Avoid adding extra load today" },
  }[value] || null;
}

function intensityCopy(value) {
  return {
    VO2: { value: "VO2 Allowed", detail: "High intensity is supported" },
    Threshold: { value: "Threshold Allowed", detail: "Controlled quality work is okay" },
    Moderate: { value: "Moderate Only", detail: "No hard intervals" },
    none: { value: "Recovery Only", detail: "Do not chase intensity" },
  }[value] || null;
}

function confidenceCopy(value) {
  return {
    High: { value: "High", detail: "Decision confidence high" },
    Medium: { value: "Moderate", detail: "Decision confidence moderate" },
    Low: { value: "Low", detail: "Use extra judgment today" },
  }[value] || null;
}
