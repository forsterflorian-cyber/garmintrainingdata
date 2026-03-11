import { safeText } from "../../lib/formatters.js";

export function setAuthStatus(text) {
  document.querySelectorAll("[data-auth-status]").forEach((target) => {
    target.textContent = safeText(text);
  });
}

export function setGarminStatus(text) {
  document.querySelectorAll("[data-garmin-status]").forEach((target) => {
    target.textContent = safeText(text);
  });
}
