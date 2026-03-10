import { el, safeText } from "../../lib/formatters.js";

export function setAuthStatus(text) {
  const target = el("authStatus");
  if (target) {
    target.textContent = safeText(text);
  }
}

export function setGarminStatus(text) {
  const target = el("garminStatus");
  if (target) {
    target.textContent = safeText(text);
  }
}
