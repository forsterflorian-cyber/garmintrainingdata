const ALLOWED_VIEWS = new Set(["plan", "analysis", "trends", "activities", "sync"]);

export function normalizedPathname() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

export function requestedViewFromHash() {
  const raw = (window.location.hash || "").replace(/^#/, "").trim().toLowerCase();
  if (!raw) {
    return "plan";
  }
  return ALLOWED_VIEWS.has(raw) ? raw : "plan";
}

export function resolveSurfaceView(view) {
  const normalized = String(view || "").trim().toLowerCase();
  return ALLOWED_VIEWS.has(normalized) ? normalized : "plan";
}

export function setHashView(view) {
  const nextView = resolveSurfaceView(view);
  const nextHash = `#${nextView}`;
  if (window.location.hash !== nextHash) {
    window.location.hash = nextHash;
  }
  return nextView;
}

export function getSelectedActivitiesDate(state) {
  return state?.selectedActivitiesDate || null;
}

export function setSelectedActivitiesDate(state, value) {
  state.selectedActivitiesDate = value || null;
  return state.selectedActivitiesDate;
}

export function clearSelectedActivitiesDate(state) {
  state.selectedActivitiesDate = null;
  return null;
}