import { el } from "../../lib/formatters.js";

export function hydrateRangeSelect(rangeFilters, selectedDays) {
  const select = el("rangeSelect");
  select.innerHTML = "";
  (rangeFilters || []).forEach((days) => {
    const option = document.createElement("option");
    option.value = String(days);
    option.textContent = days >= 365 ? "1 Jahr" : `${days} Tage`;
    option.selected = Number(days) === Number(selectedDays);
    select.appendChild(option);
  });
}
