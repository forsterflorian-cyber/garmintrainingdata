import { el, safeHtml } from "../../lib/formatters.js";

const TOAST_DURATION = 4000;
const TOAST_FADE_OUT = 300;

let toastContainer = null;
let toastId = 0;

function getToastContainer() {
  if (!toastContainer) {
    toastContainer = document.getElementById("toastContainer");
    if (!toastContainer) {
      toastContainer = document.createElement("div");
      toastContainer.id = "toastContainer";
      toastContainer.className = "toast-container";
      toastContainer.setAttribute("aria-live", "polite");
      toastContainer.setAttribute("aria-atomic", "false");
      document.body.appendChild(toastContainer);
    }
  }
  return toastContainer;
}

function createToastElement(message, { type = "info", duration = TOAST_DURATION } = {}) {
  const id = ++toastId;
  const container = getToastContainer();

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.dataset.toastId = String(id);
  toast.setAttribute("role", "alert");

  const icon = getToastIcon(type);
  const dismissible = type !== "error";

  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${icon}</span>
    <span class="toast-message">${safeHtml(message)}</span>
    ${dismissible ? '<button class="toast-dismiss" type="button" aria-label="Dismiss">×</button>' : ""}
  `;

  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add("toast-enter");
  });

  if (dismissible && duration > 0) {
    setTimeout(() => {
      dismissToast(toast);
    }, duration);
  }

  const dismissBtn = toast.querySelector(".toast-dismiss");
  if (dismissBtn) {
    dismissBtn.addEventListener("click", () => dismissToast(toast));
  }

  return id;
}

function getToastIcon(type) {
  switch (type) {
    case "success":
      return "✓";
    case "error":
      return "✕";
    case "warning":
      return "⚠";
    default:
      return "ℹ";
  }
}

function dismissToast(toast) {
  if (!toast || toast.classList.contains("toast-exit")) {
    return;
  }

  toast.classList.remove("toast-enter");
  toast.classList.add("toast-exit");

  setTimeout(() => {
    toast.remove();
  }, TOAST_FADE_OUT);
}

export function showToast(message, options = {}) {
  return createToastElement(message, options);
}

export function showSuccessToast(message, options = {}) {
  return showToast(message, { ...options, type: "success" });
}

export function showErrorToast(message, options = {}) {
  return showToast(message, { ...options, type: "error", duration: 6000 });
}

export function showWarningToast(message, options = {}) {
  return showToast(message, { ...options, type: "warning" });
}

export function showInfoToast(message, options = {}) {
  return showToast(message, { ...options, type: "info" });
}

export function dismissAllToasts() {
  const container = getToastContainer();
  container.querySelectorAll(".toast").forEach((toast) => dismissToast(toast));
}