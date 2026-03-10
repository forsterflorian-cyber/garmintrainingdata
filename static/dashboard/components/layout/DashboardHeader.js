import { el, safeText } from "../../lib/formatters.js";

export function setAuthStatus(text) {
  el("authStatus").textContent = safeText(text);
}

export function setGarminStatus(text) {
  el("garminStatus").textContent = safeText(text);
}
