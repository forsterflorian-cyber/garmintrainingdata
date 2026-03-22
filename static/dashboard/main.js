import { renderAvoidTodayPanel } from "./components/decision/AvoidTodayPanel.js";
import { renderBestOptionsPanel } from "./components/decision/BestOptionsPanel.js";
import { renderNextDaysOutlookPanel } from "./components/decision/NextDaysOutlookPanel.js";
import { renderTomorrowImpactPanel } from "./components/decision/TomorrowImpactPanel.js";
import { renderTrainingDecisionCard } from "./components/decision/TrainingDecisionCard.js";
import { renderWhyRecommendationPanel } from "./components/decision/WhyRecommendationPanel.js";
import { renderActivitiesDaySurface } from "./components/activities/ActivitiesDaySurface.js";
import { setAuthStatus, setGarminStatus } from "./components/layout/DashboardHeader.js";
import { hydrateRangeSelect } from "./components/layout/FocusFilters.js";
import { setDashboardLoadingState, syncTrainingFocusHelp } from "./components/layout/DashboardUiState.js";
import { renderBaselineComparisonCard } from "./components/metrics/BaselineComparisonCard.js";
import { renderLoadTrendCard } from "./components/trends/LoadTrendCard.js";
import { renderReadinessTrendCard } from "./components/trends/ReadinessTrendCard.js";
import { renderPrimarySyncAction, renderSyncActionButtons } from "./components/sync/SyncActionButtons.js";
import { renderSyncStatusBadge } from "./components/sync/SyncStatusBadge.js";
import { getSyncUiCopy, syncReasonLabel } from "./components/sync/syncStatusCopy.js";
import { renderSyncStatusPanel } from "./components/sync/SyncStatusPanel.js";
import {
  showToast,
  showSuccessToast,
  showErrorToast,
  showWarningToast,
  showInfoToast,
} from "./components/layout/ToastContainer.js";
import { clearPlannedSessionsForUser, getPlannedSession, setPlannedSession } from "./lib/forecastUtils.js";
import { el, formatDateTime, formatNumber, formatRelativeHours, safeHtml, safeText } from "./lib/formatters.js";
import { computeNextDaysOutlook } from "./lib/outlookForecast.js";
import { buildForecastContextCopy, compareCompletedSessionToDecision } from "./lib/planDecisionUtils.js";
import {
  updateReviewToolState,
  copyActivitiesReviewPrompt,
  importActivitiesReviewAnswer,
} from "./reviewActions.js";
import {
  historyRowsFromPayload,
  loadDashboardData,
} from "./dashboardloader.js";
import {
  normalizedPathname,
  requestedViewFromHash,
  resolveSurfaceView,
  setHashView,
} from "./viewState.js";

const APP_CONFIG = window.__APP_CONFIG__ || {};
const SURFACE_VIEWS = ["plan", "analysis", "trends", "activities", "sync", "debug"];
const APP_VIEWS = ["loading", "auth", "garminSetup", "dashboard", "settings", "error"];
const APP_ROUTE_PATHS = Object.freeze({
  auth: "/auth",
  authCallback: "/auth/callback",
  garminSetup: "/onboarding/garmin",
  dashboard: "/dashboard",
  settings: "/settings",
});
const AUTH_PROVIDERS = Object.freeze({
  password: {
    id: "password",
    kind: "password",
    label: "Email and password",
    supportedActions: ["login", "signup"],
  },
  google: {
    id: "google",
    kind: "oauth",
    label: "Google",
    oauthProvider: "google",
    supportedActions: ["login"],
  },
});
const ADVANCED_MODE_KEY = "dashboard.advancedMode";
const AUTH_REDIRECT_PROVIDER_KEY = "dashboard.auth.redirectProvider";
const SUPABASE_AUTH_STORAGE_KEY = "dashboard.supabase.auth";
const ACCOUNT_DELETE_CONFIRMATION_TEXT = "DELETE";

async function loadDashboard({ skipAutoSync = false } = {}) {
  return loadDashboardData({
    state,
    apiGet,
    setDashboardLoadingState,
    setGarminStatus,
    renderDashboard,
    renderSyncStatusPanel,
    maybeAutoSync,
    skipAutoSync,
  });
}


function loadAdvancedModePreference() {
  try {
    return window.localStorage.getItem(ADVANCED_MODE_KEY) === "true";
  } catch (_error) {
    return false;
  }
}

function resolveBrowserAuthStorage() {
  for (const storageName of ["localStorage", "sessionStorage"]) {
    try {
      const storage = window[storageName];
      if (!storage) {
        continue;
      }
      const probeKey = `__dashboard.auth.${storageName}.probe__`;
      storage.setItem(probeKey, "1");
      storage.removeItem(probeKey);
      return storage;
    } catch (_error) {
      // Try the next storage backend.
    }
  }
  return null;
}

const browserAuthStorageBackend = resolveBrowserAuthStorage();
const browserAuthStorageAvailable = Boolean(browserAuthStorageBackend);
const supabaseAuthStorage = {
  getItem(key) {
    if (!browserAuthStorageBackend) {
      return null;
    }
    try {
      return browserAuthStorageBackend.getItem(key);
    } catch (_error) {
      return null;
    }
  },
  setItem(key, value) {
    if (!browserAuthStorageBackend) {
      return;
    }
    try {
      browserAuthStorageBackend.setItem(key, value);
    } catch (_error) {
      // Ignore storage write failures and let auth methods surface the failure.
    }
  },
  removeItem(key) {
    if (!browserAuthStorageBackend) {
      return;
    }
    try {
      browserAuthStorageBackend.removeItem(key);
    } catch (_error) {
      // Ignore storage cleanup failures during auth transitions.
    }
  },
};

const state = {
  currentSession: null,
  appState: null,
  appStateError: null,
  appView: "loading",
  planDashboard: null,
  activitiesDashboard: null,
  todayDate: null,
  activitiesDate: null,
  actualSessionForPlanDate: null,
  selectedPreviewSession: null,
  forecastInputMode: "preview",
  rangeDays: APP_CONFIG.defaultRangeDays || 28,
  mode: "hybrid",
  activeView: "plan",
  advancedMode: loadAdvancedModePreference(),
  syncStatus: null,
  currentForecast: null,
  syncPollTimer: null,
  syncPollInFlight: false,
  dashboardLoadRequestId: 0,
  autoSyncKey: null,
  accountDeletionPending: false,
  sessionRestorePending: isAuthCallbackPath(window.location.pathname),
};

const supabaseClient = window.supabase && APP_CONFIG.supabaseUrl && APP_CONFIG.supabaseAnonKey
  ? window.supabase.createClient(APP_CONFIG.supabaseUrl, APP_CONFIG.supabaseAnonKey, {
      auth: {
        detectSessionInUrl: false,
        flowType: "pkce",
        persistSession: true,
        autoRefreshToken: true,
        storageKey: SUPABASE_AUTH_STORAGE_KEY,
        storage: supabaseAuthStorage,
      },
    })
  : null;

function requireSupabaseClient() {
  if (!supabaseClient) {
    throw new Error(missingConfigMessage());
  }
  return supabaseClient;
}

function missingConfigMessage() {
  const missing = APP_CONFIG.missingPublicConfig || [];
  return missing.length ? `Missing Supabase config: ${missing.join(", ")}` : "Missing Supabase config.";
}

function authCallbackUrl() {
  return `${window.location.origin}${APP_ROUTE_PATHS.authCallback}`;
}

function isAuthCallbackPath(pathname = window.location.pathname) {
  return normalizedPathname(pathname) === APP_ROUTE_PATHS.authCallback;
}

function authCallbackParams() {
  const searchParams = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return {
    code: searchParams.get("code"),
    tokenHash: searchParams.get("token_hash"),
    type: searchParams.get("type"),
    error: searchParams.get("error") || hashParams.get("error") || searchParams.get("error_code") || hashParams.get("error_code"),
    errorDescription: searchParams.get("error_description") || hashParams.get("error_description"),
    hasSessionTokens: hashParams.has("access_token") || hashParams.has("refresh_token"),
  };
}

function authCallbackPending() {
  if (!isAuthCallbackPath()) {
    return false;
  }
  const params = authCallbackParams();
  return Boolean(params.code || params.tokenHash || params.error || params.errorDescription || params.hasSessionTokens);
}

function persistPendingAuthProvider(providerId) {
  try {
    window.sessionStorage.setItem(AUTH_REDIRECT_PROVIDER_KEY, providerId);
  } catch (_error) {
    // Ignore session storage failures and continue with a generic auth message.
  }
}

function consumePendingAuthProvider() {
  try {
    const providerId = window.sessionStorage.getItem(AUTH_REDIRECT_PROVIDER_KEY);
    window.sessionStorage.removeItem(AUTH_REDIRECT_PROVIDER_KEY);
    return providerId || null;
  } catch (_error) {
    return null;
  }
}

function clearPendingAuthProvider() {
  try {
    window.sessionStorage.removeItem(AUTH_REDIRECT_PROVIDER_KEY);
  } catch (_error) {
    // Ignore session storage failures during auth cleanup.
  }
}

function isPkceVerifierError(detail = "") {
  const normalizedDetail = String(detail || "").trim().toLowerCase();
  return normalizedDetail.includes("code verifier") || normalizedDetail.includes("code_verifier");
}

function callbackFailureMessage(detail = null) {
  const providerId = consumePendingAuthProvider();
  const flowLabel = providerId === "google" ? "Google sign-in" : "Authentication";
  const cleanedDetail = String(detail || "").trim();
  if (!cleanedDetail) {
    return `${flowLabel} could not be completed. Try again.`;
  }
  if (isPkceVerifierError(cleanedDetail)) {
    return `${flowLabel} failed because the secure login state was lost. Return to ${window.location.origin}${APP_ROUTE_PATHS.auth} and try again on this origin.`;
  }
  return `${flowLabel} failed: ${cleanedDetail}`;
}

function requestedAppViewFromPath() {
  const pathname = normalizedPathname();
  if (pathname === APP_ROUTE_PATHS.auth) {
    return "auth";
  }
  if (pathname === APP_ROUTE_PATHS.authCallback) {
    return null;
  }
  if (pathname === APP_ROUTE_PATHS.garminSetup) {
    return "garminSetup";
  }
  if (pathname === APP_ROUTE_PATHS.dashboard) {
    return "dashboard";
  }
  if (pathname === APP_ROUTE_PATHS.settings) {
    return "settings";
  }
  return null;
}

function routePathForAppView(view) {
  if (view === "auth") {
    return APP_ROUTE_PATHS.auth;
  }
  if (view === "garminSetup") {
    return APP_ROUTE_PATHS.garminSetup;
  }
  if (view === "dashboard") {
    return APP_ROUTE_PATHS.dashboard;
  }
  if (view === "settings") {
    return APP_ROUTE_PATHS.settings;
  }
  return normalizedPathname();
}

function currentUserId() {
  return state.currentSession?.user?.id || null;
}

function currentUserEmail() {
  return state.currentSession?.user?.email || null;
}

function isSyncActive(syncState) {
  return syncState === "syncing" || syncState === "backfilling";
}

function isUnauthorizedError(error) {
  return Number(error?.status) === 401;
}

function debugSurfaceAllowed() {
  return Boolean(APP_CONFIG.debugMode || state.advancedMode);
}

function persistAdvancedModePreference() {
  try {
    window.localStorage.setItem(ADVANCED_MODE_KEY, String(state.advancedMode));
  } catch (_error) {
    // Ignore storage failures and keep the in-memory state.
  }
}

function syncAppLocation({ replaceHistory = false } = {}) {
  if (state.appView === "loading" && authCallbackPending()) {
    return;
  }
  const basePath = routePathForAppView(state.appView);
  const hash = state.appView === "dashboard" && state.activeView !== "plan" ? `#${state.activeView}` : "";
  const nextUrl = `${basePath}${hash}`;
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (currentUrl === nextUrl) {
    return;
  }
  const method = replaceHistory ? "replaceState" : "pushState";
  window.history[method](null, "", nextUrl);
}

function syncLocationWithView(view) {
  state.activeView = resolveSurfaceView(view);
  if (state.appView === "dashboard") {
    syncAppLocation({ replaceHistory: true });
  }
}

function syncSurfaceUi({ syncHash = true } = {}) {
  const activeView = resolveSurfaceView(state.activeView);
  state.activeView = activeView;
  const showSurfaceControls = state.appView === "dashboard";

  const debugButton = el("debugNavBtn");
  if (debugButton) {
    debugButton.hidden = !showSurfaceControls || !debugSurfaceAllowed();
  }

  const surfaceFilters = el("surfaceHeaderFilters");
  const surfaceControlRow = el("surfaceControlRow");
  const showControlRow = showSurfaceControls && !["sync", "debug"].includes(activeView);
  if (surfaceFilters) {
    surfaceFilters.hidden = !showControlRow;
  }

  if (surfaceControlRow) {
    surfaceControlRow.hidden = !showControlRow;
  }

  document.querySelectorAll("[data-view]").forEach((button) => {
    const isActive = button.dataset.view === activeView;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });

  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    const isActive = panel.dataset.viewPanel === activeView;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });

  const advancedToggle = el("advancedToggleBtn");
  if (advancedToggle) {
    const forcedOn = Boolean(APP_CONFIG.debugMode);
    advancedToggle.hidden = !showSurfaceControls || forcedOn;
    advancedToggle.setAttribute("aria-pressed", state.advancedMode ? "true" : "false");
    advancedToggle.textContent = state.advancedMode ? "Debug On" : "Debug Off";
  }

  if (syncHash) {
    syncLocationWithView(activeView);
  }
}

function setActiveView(view, options = {}) {
  state.activeView = resolveSurfaceView(view);
  syncSurfaceUi(options);
}

function updateSettingsAlert() {
  const alert = el("settingsAlert");
  if (!alert) {
    return;
  }

  if (state.appState?.garmin?.needsReconnect) {
    alert.hidden = false;
    alert.className = "status-banner status-banner-critical";
    alert.innerHTML = `
      <strong>Dashboard access is paused.</strong>
      <span>${safeHtml(state.appState.garmin.message || "Reconnect Garmin in settings.")}</span>
    `;
    return;
  }

  alert.hidden = true;
  alert.textContent = "";
  alert.className = "status-banner";
}

function updatePageTitle() {
  const labels = {
    auth: "Auth",
    garminSetup: "Garmin Setup",
    dashboard: "Dashboard",
    settings: "Settings",
    error: "Access Error",
    loading: "Loading",
  };
  document.title = `Training Decision Dashboard | ${labels[state.appView] || "Dashboard"}`;
}

function syncAppUi({ replaceHistory = false } = {}) {
  state.appView = APP_VIEWS.includes(state.appView) ? state.appView : "loading";

  document.querySelectorAll("[data-app-view]").forEach((panel) => {
    const isActive = panel.dataset.appView === state.appView;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });

  const appSectionNav = el("appSectionNav");
  const isAuthenticated = Boolean(state.currentSession?.access_token);
  if (appSectionNav) {
    const showNav = isAuthenticated && !["auth", "loading", "error", "garminSetup"].includes(state.appView);
    appSectionNav.hidden = !showNav;
    appSectionNav.querySelectorAll("[data-app-nav]").forEach((button) => {
      const targetView = button.dataset.appNav;
      const isSettings = targetView === "settings";
      const allowed = isSettings ? Boolean(state.appState?.settingsAccessible) : Boolean(state.appState?.dashboardAccessible);
      button.hidden = !showNav || !allowed;
      const isActive = targetView === state.appView;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-current", isActive ? "page" : "false");
    });
  }

  const globalLogoutBtn = el("globalLogoutBtn");
  if (globalLogoutBtn) {
    globalLogoutBtn.hidden = !isAuthenticated;
  }

  const surfaceHeaderRow = el("surfaceHeaderRow");
  if (surfaceHeaderRow) {
    surfaceHeaderRow.hidden = state.appView !== "dashboard";
  }

  const surfaceControlRow = el("surfaceControlRow");
  if (surfaceControlRow) {
    surfaceControlRow.hidden = state.appView !== "dashboard";
  }

  const settingsDashboardBtn = el("settingsDashboardBtn");
  if (settingsDashboardBtn) {
    const dashboardAllowed = Boolean(state.appState?.dashboardAccessible);
    settingsDashboardBtn.hidden = !dashboardAllowed;
    settingsDashboardBtn.disabled = !dashboardAllowed;
  }

  if (state.appView === "dashboard") {
    syncSurfaceUi({ syncHash: false });
  }

  updateSettingsAlert();
  updatePageTitle();
  syncAppLocation({ replaceHistory });
}

function setAuthUi(user) {
  const loggedIn = Boolean(user);
  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.hidden = !loggedIn;
  });

  const setupAccountEmail = el("setupAccountEmail");
  if (setupAccountEmail) {
    setupAccountEmail.textContent = user?.email ? `Account: ${user.email}` : "Account: -";
  }

  const dangerZoneAccountEmail = el("dangerZoneAccountEmail");
  if (dangerZoneAccountEmail) {
    dangerZoneAccountEmail.textContent = user?.email ? `Signed in as ${user.email}` : "Signed in as -";
  }
}

function applyCurrentSession(session) {
  state.currentSession = session || null;
  const user = state.currentSession?.user || null;
  setAuthUi(user);
  setAuthStatus(user ? `Signed in as ${user.email}` : "Not signed in");
  if (state.currentSession?.access_token) {
    clearPendingAuthProvider();
  }
}

async function completeAuthCallbackIfNeeded() {
  if (!isAuthCallbackPath()) {
    return { handled: false, session: null, message: null, missingSessionMessage: null };
  }

  try {
    const params = authCallbackParams();
    if (params.error || params.errorDescription) {
      return {
        handled: true,
        session: null,
        message: callbackFailureMessage(params.errorDescription || params.error),
        missingSessionMessage: null,
      };
    }

    if (params.tokenHash && params.type) {
      const client = requireSupabaseClient();
      const { data, error } = await client.auth.verifyOtp({
        token_hash: params.tokenHash,
        type: params.type,
      });
      if (error) {
        return {
          handled: true,
          session: null,
          message: callbackFailureMessage(error.message),
          missingSessionMessage: null,
        };
      }
      return {
        handled: true,
        session: data?.session || null,
        message: null,
        missingSessionMessage: data?.session ? null : "Confirmation completed. Sign in to continue.",
      };
    }

    if (!params.code) {
      return { handled: false, session: null, message: null, missingSessionMessage: null };
    }

    const client = requireSupabaseClient();
    const { data, error } = await client.auth.exchangeCodeForSession(params.code);
    if (error) {
      return {
        handled: true,
        session: null,
        message: callbackFailureMessage(error.message),
        missingSessionMessage: null,
      };
    }

    return {
      handled: true,
      session: data?.session || null,
      message: null,
      missingSessionMessage: null,
    };
  } catch (error) {
    return {
      handled: true,
      session: null,
      message: callbackFailureMessage(error?.message || "Unexpected callback error."),
      missingSessionMessage: null,
    };
  }
}

function buildApiError(response, payload) {
  const error = new Error(payload?.error || `HTTP ${response.status}`);
  error.status = response.status;
  return error;
}

async function getToken() {
  requireSupabaseClient();
  const token = state.currentSession?.access_token || null;
  if (!token) {
    const error = new Error("Sign in first.");
    error.status = 401;
    throw error;
  }
  return token;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTransientError(error) {
  if (error.message?.includes("Failed to fetch")) return true;
  if (error.message?.includes("NetworkError")) return true;
  if (error.status >= 500 && error.status < 600) return true;
  return false;
}

function getUserFriendlyErrorMessage(error) {
  const message = error.message || "Unknown error";

  if (message.includes("timed out")) {
    return "The request took too long. Please check your connection and try again.";
  }
  if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
    return "Unable to connect to the server. Please check your internet connection.";
  }
  if (message.includes("401") || message.includes("Unauthorized")) {
    return "Your session has expired. Please sign in again.";
  }
  if (message.includes("403") || message.includes("Forbidden")) {
    return "You do not have permission to perform this action.";
  }
  if (message.includes("404") || message.includes("Not Found")) {
    return "The requested resource was not found.";
  }
  if (message.includes("500") || message.includes("Internal Server Error")) {
    return "Something went wrong on our end. Please try again later.";
  }

  return message;
}

function showErrorToUser(error, context = "") {
  const friendlyMessage = getUserFriendlyErrorMessage(error);
  const fullMessage = context ? `${context}: ${friendlyMessage}` : friendlyMessage;
  showErrorToast(fullMessage);
  console.error("User-facing error:", error);
}

async function apiGet(url, options = {}) {
  const token = await getToken();
  const { timeout = 30000, retries = 0 } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    let json;
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      try {
        json = await response.json();
      } catch (parseError) {
        throw new Error(`Invalid JSON response from ${url}: ${parseError.message}`);
      }
    } else {
      const text = await response.text();
      throw new Error(`Expected JSON response but got: ${text.substring(0, 100)}`);
    }

    if (!response.ok) {
      throw buildApiError(response, json);
    }

    return json;
  } catch (error) {
    clearTimeout(timeoutId);

    if (error.name === "AbortError") {
      throw new Error(`Request to ${url} timed out after ${timeout}ms`);
    }

    if (retries > 0 && isTransientError(error)) {
      await sleep(1000);
      return apiGet(url, { ...options, retries: retries - 1 });
    }

    throw error;
  }
}

async function apiPost(url, body = null, options = {}) {
  const token = await getToken();
  const { timeout = 30000, retries = 0 } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : null,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    let json;
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      try {
        json = await response.json();
      } catch (parseError) {
        throw new Error(`Invalid JSON response from ${url}: ${parseError.message}`);
      }
    } else {
      const text = await response.text();
      throw new Error(`Expected JSON response but got: ${text.substring(0, 100)}`);
    }

    if (!response.ok) {
      throw buildApiError(response, json);
    }

    return json;
  } catch (error) {
    clearTimeout(timeoutId);

    if (error.name === "AbortError") {
      throw new Error(`Request to ${url} timed out after ${timeout}ms`);
    }

    if (retries > 0 && isTransientError(error)) {
      await sleep(1000);
      return apiPost(url, body, { ...options, retries: retries - 1 });
    }

    throw error;
  }
}

function authProvider(providerId) {
  return AUTH_PROVIDERS[providerId] || null;
}

function authCredentials() {
  return {
    email: el("authEmail")?.value.trim() || "",
    password: el("authPassword")?.value || "",
  };
}

function garminFieldIdsForContext(context) {
  return context === "settings"
    ? { emailId: "settingsGarminEmail", passwordId: "settingsGarminPassword" }
    : { emailId: "setupGarminEmail", passwordId: "setupGarminPassword" };
}

function garminCredentialsForContext(context) {
  const { emailId, passwordId } = garminFieldIdsForContext(context);
  return {
    email: el(emailId)?.value.trim() || "",
    password: el(passwordId)?.value.trim() || "",
  };
}

function accountDeletionInputValue() {
  return el("deleteAccountConfirmInput")?.value.trim() || "";
}

function isAccountDeletionConfirmed() {
  return accountDeletionInputValue() === ACCOUNT_DELETE_CONFIRMATION_TEXT;
}

function setAccountDeletionFeedback(message, { tone = "default" } = {}) {
  const feedback = el("deleteAccountFeedback");
  if (!feedback) {
    return;
  }

  feedback.className = "danger-feedback";
  if (tone === "error") {
    feedback.classList.add("is-error");
  } else if (tone === "success") {
    feedback.classList.add("is-success");
  }
  feedback.textContent = message || "This action cannot be undone.";
}

function syncAccountDeletionUi() {
  const launchButton = el("deleteAccountBtn");
  const confirmPanel = el("deleteAccountConfirmPanel");
  const input = el("deleteAccountConfirmInput");
  const confirmButton = el("confirmDeleteAccountBtn");
  const cancelButton = el("cancelDeleteAccountBtn");
  const busy = state.accountDeletionPending;

  if (launchButton) {
    launchButton.disabled = busy;
  }
  if (input) {
    input.disabled = busy;
  }
  if (confirmButton) {
    confirmButton.disabled = busy || !isAccountDeletionConfirmed();
  }
  if (cancelButton) {
    cancelButton.disabled = busy;
  }
  if (confirmPanel) {
    confirmPanel.dataset.busy = busy ? "true" : "false";
  }
}

function resetAccountDeletionUi() {
  state.accountDeletionPending = false;
  const confirmPanel = el("deleteAccountConfirmPanel");
  const input = el("deleteAccountConfirmInput");
  if (confirmPanel) {
    confirmPanel.hidden = true;
  }
  if (input) {
    input.value = "";
  }
  setAccountDeletionFeedback("This action cannot be undone.");
  syncAccountDeletionUi();
}

function openAccountDeletionConfirmation() {
  const confirmPanel = el("deleteAccountConfirmPanel");
  if (!confirmPanel) {
    return;
  }
  confirmPanel.hidden = false;
  setAccountDeletionFeedback("This action cannot be undone.");
  syncAccountDeletionUi();
  el("deleteAccountConfirmInput")?.focus();
}

function clearUserLocalState(userId) {
  clearPlannedSessionsForUser(userId);
}

function resolveAllowedAppView(preferredView = requestedAppViewFromPath()) {
  if (!state.currentSession?.access_token) {
    return "auth";
  }
  if (state.appStateError) {
    return "error";
  }
  if (!state.appState) {
    return "loading";
  }
  if (state.appState.phase === "garmin_setup") {
    return "garminSetup";
  }
  if (state.appState.phase === "settings") {
    return "settings";
  }
  if (preferredView === "settings") {
    return "settings";
  }
  return "dashboard";
}

function applyAppState(appState) {
  state.appState = appState;
  state.appStateError = null;
  state.syncStatus = appState?.sync || null;
  setGarminStatus(appState?.garmin?.message || "Garmin status unavailable.");
  renderSyncStatusPanel(state.syncStatus || {}, "settingsSyncStatusPanel");
  updateSettingsAlert();
}

async function activateAppView(view, { replaceHistory = false, loadDashboardIfNeeded = true } = {}) {
  state.appView = view;
  if (view !== "dashboard") {
    stopSyncPolling();
  }
  syncAppUi({ replaceHistory });

  if (view === "dashboard" && loadDashboardIfNeeded) {
    await loadDashboard();
  } else if (view !== "dashboard") {
    renderSyncStatusPanel(state.syncStatus || {}, "settingsSyncStatusPanel");
  }
}

async function refreshAppState({ requestedView = requestedAppViewFromPath(), replaceHistory = false, loadDashboardIfNeeded = true } = {}) {
  if (!state.currentSession?.access_token) {
    setLoggedOutState();
    return;
  }

  try {
    const payload = await apiGet("/api/app-state");
    applyAppState(payload);
    await activateAppView(resolveAllowedAppView(requestedView), { replaceHistory, loadDashboardIfNeeded });
  } catch (error) {
    if (isUnauthorizedError(error)) {
      await handleUnauthorizedSession("Session expired. Sign in again.");
      return;
    }
    state.appStateError = error.message;
    const errorMessage = el("appErrorMessage");
    if (errorMessage) {
      errorMessage.textContent = `App state could not be loaded: ${error.message}`;
    }
    await activateAppView("error", { replaceHistory, loadDashboardIfNeeded: false });
  }
}

function dashboardUrlForDate(date = null) {
  const params = new URLSearchParams({
    days: String(state.rangeDays),
    mode: state.mode,
  });
  if (date) {
    params.set("date", date);
  }
  return `/api/dashboard?${params.toString()}`;
}

function currentBestOptions() {
  return state.planDashboard?.decision?.bestOptions || [];
}

function getStoredPlannedSession() {
  return getPlannedSession(currentUserId(), state.todayDate || state.planDashboard?.date);
}

function validPlannedSessionType() {
  const plannedType = getStoredPlannedSession();
  if (plannedType && currentBestOptions().some((option) => option.type === plannedType)) {
    return plannedType;
  }
  return currentBestOptions()[0]?.type || null;
}

function setStoredPlannedSessionType(sessionType) {
  const todayDate = state.todayDate || state.planDashboard?.date;
  setPlannedSession(currentUserId(), todayDate, sessionType);
  state.selectedPreviewSession = sessionType || null;
}

function syncStatusSummary(sync) {
  if (!sync?.syncState) {
    return "No Sync Data Yet.";
  }
  const display = getSyncUiCopy(sync);
  const summaryLines = [display.summaryText, display.detail, ...display.advisoryLines].filter(Boolean);
  if (summaryLines.length) {
    return summaryLines.join(". ");
  }
  if (sync.lastErrorMessage && !display.suppressLastError) {
    return sync.lastErrorMessage;
  }
  if (sync.lastSuccessfulSyncAt) {
    return `Last Success ${formatDateTime(sync.lastSuccessfulSyncAt)}`;
  }
  if (sync.syncState === "never_synced") {
    return "No Successful Sync Yet.";
  }
  return sync.statusReason ? display.reasonLabel || syncReasonLabel(sync.statusReason) : "No Sync Detail.";
}

function syncBackfillDays() {
  const days = Number(state.syncStatus?.targetHistoryDays);
  if (Number.isFinite(days) && days > 0) {
    return Math.trunc(days);
  }
  return 180;
}

function renderSyncUi(sync = state.syncStatus) {
  renderSyncStatusBadge(sync || {});
  renderSyncStatusPanel(sync || {});
  renderSyncActionButtons(sync || {});
  renderPrimarySyncAction(sync || {});
  renderSyncStatusPanel(sync || {}, "settingsSyncStatusPanel");
  bindSyncActionButtons();

  if (el("planSyncMeta")) {
    el("planSyncMeta").textContent = planSyncMeta(sync);
  }

  if (el("snapshotSyncStatus")) {
    el("snapshotSyncStatus").textContent = safeText(getSyncUiCopy(sync || {}).headline);
  }
  if (el("snapshotSyncMeta")) {
    el("snapshotSyncMeta").textContent = syncStatusSummary(sync);
  }
}

function setActivitiesDay(date) {
  if (!date || date === state.activitiesDate) {
    return;
  }
  state.activitiesDate = date;
  void loadDashboard({ skipAutoSync: true });
}

function historyDates(rows) {
  return rows
    .map((row) => (typeof row?.date === "string" && row.date ? row.date : null))
    .filter(Boolean);
}

function resolveActivitiesDate(requestedDate, todayPayload) {
  const dates = historyDates(historyRowsFromPayload(todayPayload));
  if (!dates.length) {
    return typeof todayPayload?.date === "string" && todayPayload.date ? todayPayload.date : null;
  }
  if (requestedDate && dates.includes(requestedDate)) {
    return requestedDate;
  }
  if (todayPayload?.date && dates.includes(todayPayload.date)) {
    return todayPayload.date;
  }
  return dates[dates.length - 1];
}

function safeNumeric(value) {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

function primaryActivityForActivities(activities) {
  return activities.slice().sort((left, right) => {
    const leftLoad = safeNumeric(left?.training_load) || 0;
    const rightLoad = safeNumeric(right?.training_load) || 0;
    if (leftLoad !== rightLoad) {
      return rightLoad - leftLoad;
    }
    const leftDuration = safeNumeric(left?.duration_min) || 0;
    const rightDuration = safeNumeric(right?.duration_min) || 0;
    return rightDuration - leftDuration;
  })[0] || null;
}

function weightedAverage(activities, valueKey, weightKey) {
  let weightedSum = 0;
  let totalWeight = 0;

  activities.forEach((activity) => {
    const value = safeNumeric(activity?.[valueKey]);
    const weight = safeNumeric(activity?.[weightKey]) || 0;
    if (value === null || weight <= 0) {
      return;
    }
    weightedSum += value * weight;
    totalWeight += weight;
  });

  if (totalWeight <= 0) {
    return null;
  }
  return weightedSum / totalWeight;
}

function labelFromKey(value) {
  if (!value) {
    return null;
  }
  return String(value)
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function sessionCategoryLabel(category) {
  return {
    recovery: "Recovery",
    easy: "Easy",
    moderate: "Moderate",
    threshold: "Threshold",
    vo2: "VO2",
    heavy_strength: "Strength",
    light_strength: "Light Strength",
  }[category] || labelFromKey(category) || "Session";
}

function actualSessionTitle(activity, sessionType) {
  if (activity?.name && String(activity.name).trim() && String(activity.name).trim().toLowerCase() !== "unknown") {
    return String(activity.name).trim();
  }
  return labelFromKey(activity?.type_key) || sessionCategoryLabel(sessionType);
}

function resolveActualSessionForPlanDate(payload) {
  const activities = payload?.today?.activities || payload?.detail?.activities || [];
  if (!activities.length) {
    return null;
  }

  const sessionType = payload?.today?.sessionType || payload?.detail?.sessionType || "easy";
  const primaryActivity = primaryActivityForActivities(activities);
  const totalDuration = activities.reduce((sum, activity) => sum + (safeNumeric(activity?.duration_min) || 0), 0);
  const avgHr = weightedAverage(activities, "avg_hr", "duration_min") ?? safeNumeric(primaryActivity?.avg_hr);
  const totalLoad = activities.reduce((sum, activity) => sum + (safeNumeric(activity?.training_load) || 0), 0);
  const aerobicTe = activities.reduce((sum, activity) => sum + (safeNumeric(activity?.aerobic_te) || 0), 0);
  const anaerobicTe = activities.reduce((sum, activity) => sum + (safeNumeric(activity?.anaerobic_te) || 0), 0);
  const title = activities.length === 1
    ? actualSessionTitle(primaryActivity, sessionType)
    : `${activities.length} activities completed`;
  const summary = [
    sessionCategoryLabel(sessionType),
    totalDuration > 0 ? `${formatNumber(totalDuration, 0)} min` : null,
    avgHr !== null ? `Avg HR ${formatNumber(avgHr, 0)}` : null,
  ].filter(Boolean).join(" / ");
  const chips = [
    totalLoad > 0 ? `Load ${formatNumber(totalLoad, 0)}` : null,
    aerobicTe > 0 || anaerobicTe > 0 ? `TE ${formatNumber(aerobicTe, 1)} / ${formatNumber(anaerobicTe, 1)}` : null,
  ].filter(Boolean);

  return {
    type: sessionType,
    label: summary || title,
    title,
    summary,
    chips,
    durationMinutes: totalDuration > 0 ? totalDuration : null,
  };
}

function planForecastMeta(forecastInputMode) {
  return forecastInputMode === "actual"
    ? "Completed session drives tomorrow and the next days."
    : "Preview selection drives tomorrow and the next days.";
}

function renderPlanSessionSection({ actualSession, options, selectedType, sessionComparison = null }) {
  const actualCard = el("planActualSessionCard");
  const sessionGrid = el("decisionSessionGrid");
  const comparison = el("planSessionComparison");
  const actualMode = Boolean(actualSession);

  el("planSessionLabel").textContent = "What you should do today";
  el("planSessionTitle").textContent = "Recommended sessions";
  el("planSessionMeta").textContent = actualMode
    ? "Recommendations stay visible alongside what you completed today."
    : "Selection updates tomorrow and the next days outlook.";

  const completedNotice = el("planCompletedNotice");
  if (completedNotice) {
    completedNotice.hidden = !actualMode;
    completedNotice.textContent = actualMode
      ? "Today\u2019s sessions are already recorded. These recommendations are now informational and influence tomorrow\u2019s plan."
      : "";
  }

  if (actualMode) {
    const actualLabel = el("planActualSessionLabel");
    if (actualLabel) {
      actualLabel.textContent = "What you did today";
    }
    el("planActualSessionTitle").textContent = safeText(actualSession.title, "Completed session");
    el("planActualSessionSummary").textContent = safeText(actualSession.summary, "Tomorrow uses the completed session.");
    el("planActualSessionStats").innerHTML = actualSession.chips.length
      ? actualSession.chips.map((chip) => `<span class="chip">${safeHtml(chip)}</span>`).join("")
      : "";
    actualCard.hidden = false;
    comparison.textContent = safeText(sessionComparison?.label);
    comparison.dataset.tone = sessionComparison?.tone || "neutral";
    comparison.hidden = !sessionComparison?.label;
  } else {
    actualCard.hidden = true;
    el("planActualSessionStats").innerHTML = "";
    comparison.hidden = true;
    comparison.textContent = "";
    comparison.dataset.tone = "neutral";
  }

  sessionGrid.hidden = false;
  renderBestOptionsPanel(options, { selectedType, completed: actualMode });
}

function renderDecisionPanels(payload) {
  const options = currentBestOptions();
  const selectedType = validPlannedSessionType();
  if (selectedType && selectedType !== getStoredPlannedSession()) {
    setStoredPlannedSessionType(selectedType);
  }

  state.selectedPreviewSession = selectedType;
  state.actualSessionForPlanDate = resolveActualSessionForPlanDate(payload);
  state.forecastInputMode = state.actualSessionForPlanDate ? "actual" : "preview";

  renderTrainingDecisionCard({
    payload,
    targetDayLabel: payload?.date ? `Today: ${payload.date}` : "-",
    targetMeta: planForecastMeta(state.forecastInputMode),
  });
  renderAvoidTodayPanel(payload?.decision?.avoid || []);
  renderPlanSessionSection({
    actualSession: state.actualSessionForPlanDate,
    options,
    selectedType,
    sessionComparison: state.actualSessionForPlanDate
      ? compareCompletedSessionToDecision(state.actualSessionForPlanDate.type, payload?.decision)
      : null,
  });
  if (state.forecastInputMode === "preview") {
    bindPlannedSessionButtons();
  }

  const selectedOption = options.find((option) => option.type === selectedType) || null;
  const forecastSession = state.forecastInputMode === "actual"
    ? state.actualSessionForPlanDate
    : selectedOption;
  const forecastContext = buildForecastContextCopy(forecastSession, {
    forecastInputMode: state.forecastInputMode,
  });
  const tomorrowContext = state.forecastInputMode === "actual"
    ? "Based on today's completed session."
    : "Based on today's preview.";
  const outlook = computeNextDaysOutlook({
    currentDecision: payload?.decision,
    currentMetrics: payload?.today,
    currentLoad: payload?.load,
    currentComparisons: payload?.comparisons,
    baseline: payload?.baseline,
    selectedSession: forecastSession,
    currentDate: payload?.today?.recommendationDay || payload?.date,
    mode: payload?.mode,
    days: 4,
  });

  state.currentForecast = outlook;
  renderTomorrowImpactPanel({
    impact: outlook?.tomorrowImpact,
    plannedOptionLabel: forecastSession?.label || null,
    forecastInputMode: state.forecastInputMode,
    sourceContext: tomorrowContext,
  });
  renderNextDaysOutlookPanel(outlook, {
    forecastInputMode: state.forecastInputMode,
    sourceContext: state.forecastInputMode === "actual"
      ? "Forecast follows today's completed session."
      : "Preview follows the selected session.",
  });
}

function renderSummary(payload) {
  el("summaryAverageReadiness").textContent = formatNumber(payload?.summary?.avgReadiness, 1);
  el("summaryAverageLoad").textContent = formatNumber(payload?.summary?.avgLoad, 1);
  el("snapshotFocusDate").textContent = safeText(payload?.date);
  el("snapshotWindow").textContent = `${safeText(payload?.filters?.periodDays)}d trailing / ${safeText(payload?.reference?.baselineDays)}d baseline`;
  el("snapshotRatio").textContent = formatNumber(payload?.load?.ratio7to28, 2);
  el("snapshotStress").textContent = safeText(payload?.decision?.loadTolerance);
  el("snapshotModelRecommendation").textContent = safeText(payload?.decision?.primaryRecommendation);
  if (el("baselineReferenceCopy")) {
    const sampleDays = Number(payload?.reference?.baselineSampleDays || 0);
    const baselineDays = safeText(payload?.reference?.baselineDays, "");
    if (payload?.reference?.baselineSource === "rolling" && baselineDays) {
      el("baselineReferenceCopy").textContent = `Rolling ${baselineDays}-day reference ending before today. Load ratio stays on 7d / 28d. ${sampleDays ? `Samples used: ${sampleDays} days.` : ""}`.trim();
    } else if (baselineDays) {
      el("baselineReferenceCopy").textContent = `Stored Garmin baseline shown because the ${baselineDays}-day range does not yet have enough prior samples. Load ratio stays on 7d / 28d.`;
    } else {
      el("baselineReferenceCopy").textContent = "Reference window follows the selected range. Load ratio stays on 7d / 28d.";
    }
  }
}

function renderDebug(payload, forecast) {
  const decisionDebug = payload?.debug || payload?.decision?.debug || {};
  const sync = payload?.sync || null;
  const syncDebug = sync?.debug || null;
  const lines = [];

  if (decisionDebug.recoveryScore !== undefined) {
    lines.push(`recoveryScore=${formatNumber(decisionDebug.recoveryScore, 2)}`);
  }
  if (decisionDebug.loadToleranceScore !== undefined) {
    lines.push(`loadToleranceScore=${formatNumber(decisionDebug.loadToleranceScore, 2)}`);
  }
  if (decisionDebug.ratio7to28 !== undefined && decisionDebug.ratio7to28 !== null) {
    lines.push(`ratio7to28=${formatNumber(decisionDebug.ratio7to28, 2)}`);
  }
  if (decisionDebug.hardSessionsLast3d !== undefined) {
    lines.push(`hardSessionsLast3d=${safeText(decisionDebug.hardSessionsLast3d)}`);
  }
  (decisionDebug.selectedRulePath || []).forEach((line) => lines.push(line));
  if (sync) {
    lines.push(`syncState=${safeText(sync.syncState)}`);
    lines.push(`syncReason=${safeText(sync.statusReason)}`);
    lines.push(`syncLock=${safeText(sync.isLocked)}`);
    lines.push(`syncCooldownUntil=${safeText(sync.cooldownUntil)}`);
    lines.push(`syncLastErrorCode=${safeText(sync.lastErrorCode)}`);
    lines.push(`syncMissingDays=${safeText(sync.missingDaysCount)}`);
  }
  if (syncDebug) {
    lines.push(`syncCooldownActive=${safeText(syncDebug.cooldownActive)}`);
  }

  el("debugList").innerHTML = lines.length
    ? lines.map((line) => `<div class="debug-line">${safeHtml(line)}</div>`).join("")
    : '<div class="muted-copy">No debug trace available for the selected day.</div>';

  const forecastLines = [];
  if (forecast?.trace?.initialState) {
    forecastLines.push(`initialRecoveryScore=${formatNumber(forecast.trace.initialState.recoveryScore, 2)}`);
    forecastLines.push(`initialLoadRatio=${formatNumber(forecast.trace.initialState.loadRatio, 2)}`);
    forecastLines.push(`initialHardSessionsLast3d=${safeText(forecast.trace.initialState.hardSessionsLast3d)}`);
    forecastLines.push(`initialHardSessionsLast7d=${safeText(forecast.trace.initialState.hardSessionsLast7d)}`);
    forecastLines.push(`initialLastSessionType=${safeText(forecast.trace.initialState.lastSessionType)}`);
    forecastLines.push(`selectedSessionCategory=${safeText(forecast.trace.selectedSessionCategory)}`);
    forecastLines.push(`selectedSessionType=${safeText(forecast.trace.selectedSessionType)}`);
  }
  (forecast?.trace?.days || []).forEach((day) => {
    forecastLines.push(`${day.label}: recoveryScore=${formatNumber(day.recoveryScore, 2)}`);
    forecastLines.push(`${day.label}: loadRatio=${formatNumber(day.loadRatio, 2)}`);
    forecastLines.push(`${day.label}: rawIntensity=${safeText(day.rawIntensityPermission)}`);
    if (day.qualityBlocks?.length) {
      forecastLines.push(`${day.label}: blocks=${day.qualityBlocks.join("; ")}`);
    }
    forecastLines.push(`${day.label}: recommendation=${safeText(day.recommendation)}`);
    forecastLines.push(`${day.label}: defaultSession=${safeText(day.defaultSessionCategory)}`);
  });

  const forecastTarget = el("forecastDebugList");
  if (forecastTarget) {
    forecastTarget.innerHTML = forecastLines.length
      ? forecastLines.map((line) => `<div class="debug-line">${safeHtml(line)}</div>`).join("")
      : '<div class="muted-copy">No forecast trace available for the selected day.</div>';
  }
}

function renderPrompt(payload) {
  const promptField = el("aiPrompt");
  if (promptField) {
    promptField.value = payload?.detail?.aiPrompt || "";
  }
}

function renderPlanSurface(payload) {
  if (!payload || !payload.history?.rows?.length) {
    state.currentForecast = null;
    state.actualSessionForPlanDate = null;
    state.selectedPreviewSession = null;
    state.forecastInputMode = "preview";
    renderPlanSessionSection({ actualSession: null, options: [], selectedType: null });
    renderTrainingDecisionCard({ payload: payload || {} });
    renderAvoidTodayPanel([]);
    renderTomorrowImpactPanel({ impact: null, plannedOptionLabel: null, forecastInputMode: "preview" });
    renderNextDaysOutlookPanel(null, { forecastInputMode: "preview" });
    return;
  }

  renderDecisionPanels(payload);
}

function renderAnalysisSurface(payload) {
  renderWhyRecommendationPanel(payload?.decision?.why || []);
  renderBaselineComparisonCard(payload?.baselineBars || [], {
    targetId: "analysisBaselineMetricList",
    emptyCopy: "No baseline comparison available for today.",
  });
  renderPrompt(payload || {});
  renderSummary(payload || {});
}

function renderTrendsSurface(payload) {
  renderReadinessTrendCard(payload?.trends?.readinessSeries || [], payload?.date || null);
  renderLoadTrendCard(
    payload?.trends?.loadChannelSeries || payload?.trends?.loadSeries || [],
    payload?.date || null,
    payload?.load?.momentum || null,
  );
}

function renderActivitiesSurface(payload, availableDays) {
  renderActivitiesDaySurface(payload || {}, {
    availableDays,
    selectedDate: state.activitiesDate,
    onSelectDay: setActivitiesDay,
    mode: state.mode,
    todayDate: state.todayDate || state.planDashboard?.date || null,
  });

  renderActivitiesReviewStatus(payload || {});
}

function renderDashboard() {
  const planPayload = state.planDashboard;
  renderSyncUi(planPayload?.sync || state.syncStatus);
  renderPlanSurface(planPayload);
  renderAnalysisSurface(planPayload || {});
  renderTrendsSurface(planPayload || {});
  renderActivitiesSurface(
    state.activitiesDashboard || planPayload || {},
    historyRowsFromPayload(planPayload)
  );
  renderDebug(planPayload || state.activitiesDashboard || {}, state.currentForecast);
  updateReviewToolState({ state, el });
}

async function refreshSyncStatus({ reloadDashboardOnTerminal = false } = {}) {
  if (!state.currentSession?.access_token || state.syncPollInFlight) {
    return;
  }

  state.syncPollInFlight = true;
  const previousState = state.syncStatus?.syncState;
  try {
    const payload = await apiGet("/api/sync/status");
    state.syncStatus = payload;
    renderSyncUi(payload);
    if (payload.syncState === "blocked") {
      await refreshAppState({ requestedView: "settings", replaceHistory: true, loadDashboardIfNeeded: false });
      return;
    }
    if (isSyncActive(payload.syncState)) {
      startSyncPolling();
    } else {
      stopSyncPolling();
      if (reloadDashboardOnTerminal && isSyncActive(previousState)) {
        await loadDashboard({ skipAutoSync: true });
      }
    }
  } catch (error) {
    stopSyncPolling();
    if (isUnauthorizedError(error)) {
      await handleUnauthorizedSession("Session expired. Sign in again.");
      return;
    }
    setGarminStatus(`Sync status error: ${error.message}`);
  } finally {
    state.syncPollInFlight = false;
  }
}

function startSyncPolling() {
  if (state.syncPollTimer) {
    return;
  }
  state.syncPollTimer = window.setInterval(() => {
    void refreshSyncStatus({ reloadDashboardOnTerminal: true });
  }, 5000);
}

function stopSyncPolling() {
  if (!state.syncPollTimer) {
    return;
  }
  window.clearInterval(state.syncPollTimer);
  state.syncPollTimer = null;
}

async function startSyncRequest(url, body, optimisticState) {
  state.syncStatus = {
    ...(state.syncStatus || {}),
    syncState: optimisticState,
    canStartSync: false,
  };
  renderSyncUi(state.syncStatus);
  startSyncPolling();

  try {
    const response = await apiPost(url, body);
    state.syncStatus = response;
    renderSyncUi(response);
    if (response.syncState === "blocked") {
      await refreshAppState({ requestedView: "settings", replaceHistory: true, loadDashboardIfNeeded: false });
      return;
    }
    if (isSyncActive(response.syncState)) {
      startSyncPolling();
    } else {
      stopSyncPolling();
      if (state.appView === "dashboard") {
        await loadDashboard({ skipAutoSync: true });
      } else {
        await refreshAppState({ requestedView: state.appView, replaceHistory: true, loadDashboardIfNeeded: false });
      }
    }
  } catch (error) {
    if (isUnauthorizedError(error)) {
      await handleUnauthorizedSession("Session expired. Sign in again.");
      return;
    }
    setGarminStatus(`Sync error: ${error.message}`);
    await refreshSyncStatus({ reloadDashboardOnTerminal: false });
  }
}

function maybeAutoSync() {
  if (state.appView !== "dashboard") {
    return;
  }
  const sync = state.planDashboard?.sync;
  if (!sync?.autoSyncEnabled || !sync?.autoSyncRecommended) {
    return;
  }

  const key = [
    currentUserId() || "anon",
    sync.syncState || "unknown",
    sync.autoSyncMode || "none",
    sync.lastSuccessfulSyncAt || "never",
    sync.statusReason || "none",
  ].join(":");
  if (state.autoSyncKey === key) {
    return;
  }

  state.autoSyncKey = key;
  const optimisticState = sync.autoSyncMode === "backfill" ? "backfilling" : "syncing";
  setGarminStatus(sync.autoSyncMode === "backfill" ? "Auto Backfill Started..." : "Auto Sync Started...");
  void startSyncRequest("/api/sync/auto", null, optimisticState);
}


function setLoggedOutState({ authMessage = "Not signed in", garminMessage = "Sign in to connect Garmin." } = {}) {
  state.appState = null;
  state.appStateError = null;
  state.appView = "auth";
  state.planDashboard = null;
  state.activitiesDashboard = null;
  state.todayDate = null;
  state.activitiesDate = null;
  state.actualSessionForPlanDate = null;
  state.selectedPreviewSession = null;
  state.forecastInputMode = "preview";
  state.currentForecast = null;
  state.syncStatus = null;
  state.autoSyncKey = null;
  state.dashboardLoadRequestId += 1;
  stopSyncPolling();
  setDashboardLoadingState(false);
  resetAccountDeletionUi();
  renderDashboard();
  renderSyncStatusPanel({}, "settingsSyncStatusPanel");
  setAuthUi(null);
  setAuthStatus(authMessage);
  setGarminStatus(garminMessage);
  syncAppUi({ replaceHistory: true });
}

async function handleUnauthorizedSession(message) {
  if (supabaseClient) {
    try {
      await supabaseClient.auth.signOut();
    } catch (_error) {
      // Ignore sign-out cleanup errors and still reset the local state.
    }
  }
  clearPendingAuthProvider();
  applyCurrentSession(null);
  setLoggedOutState({ authMessage: message, garminMessage: message });
}

async function performAuthAction(action, providerId) {
  const provider = authProvider(providerId);
  if (!provider || !provider.supportedActions.includes(action)) {
    setAuthStatus("This authentication method is not available.");
    return;
  }

  const client = requireSupabaseClient();
  if (provider.kind === "oauth") {
    if (!browserAuthStorageAvailable) {
      setAuthStatus(`Google sign-in requires browser storage on ${window.location.origin}. Enable local or session storage and try again.`);
      return;
    }
    persistPendingAuthProvider(provider.id);
    setAuthStatus(`Redirecting to ${provider.label}...`);
    const { error } = await client.auth.signInWithOAuth({
      provider: provider.oauthProvider,
      options: {
        redirectTo: authCallbackUrl(),
      },
    });
    if (error) {
      clearPendingAuthProvider();
      setAuthStatus(error.message);
    }
    return;
  }

  const { email, password } = authCredentials();
  if (!email || !password) {
    setAuthStatus("Enter email and password.");
    return;
  }

  if (action === "login") {
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) {
      setAuthStatus(error.message);
      return;
    }
    setAuthStatus("Signed in. Loading session...");
    return;
  }

  const { error } = await client.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: authCallbackUrl() },
  });
  if (error) {
    setAuthStatus(error.message);
    return;
  }
  setAuthStatus("Sign-up started. Confirm your email if required.");
}

async function logout() {
  if (supabaseClient) {
    await supabaseClient.auth.signOut();
  }
  clearPendingAuthProvider();
  applyCurrentSession(null);
  setLoggedOutState();
}

async function deleteAccount() {
  if (!isAccountDeletionConfirmed() || state.accountDeletionPending) {
    setAccountDeletionFeedback("Type DELETE to confirm account deletion.", { tone: "error" });
    syncAccountDeletionUi();
    return;
  }

  const userId = currentUserId();
  state.accountDeletionPending = true;
  setAccountDeletionFeedback("Deleting account...");
  syncAccountDeletionUi();

  try {
    const response = await apiPost("/api/account/delete", {
      confirmationText: accountDeletionInputValue(),
    });

    clearUserLocalState(userId);
    if (supabaseClient) {
      try {
        await supabaseClient.auth.signOut();
      } catch (_error) {
        // Ignore sign-out cleanup failures after the account has already been deleted.
      }
    }

    clearPendingAuthProvider();
    applyCurrentSession(null);
    setLoggedOutState({
      authMessage: "Account deleted.",
      garminMessage: "Account deleted.",
    });

    const redirectTo = typeof response?.redirectTo === "string" ? response.redirectTo : APP_ROUTE_PATHS.auth;
    if (normalizedPathname() !== redirectTo) {
      window.history.replaceState(null, "", redirectTo);
    }
  } catch (error) {
    if (isUnauthorizedError(error)) {
      await handleUnauthorizedSession("Session expired. Sign in again.");
      return;
    }

    state.accountDeletionPending = false;
    setAccountDeletionFeedback(
      error?.message || "Account deletion could not be completed. Please try again.",
      { tone: "error" },
    );
    syncAccountDeletionUi();
  }
}

async function submitGarminCredentials(context) {
  try {
    const { email, password } = garminCredentialsForContext(context);
    if (!email || !password) {
      setGarminStatus("Enter Garmin email and password.");
      return;
    }
    setGarminStatus("Checking Garmin credentials...");
    await apiPost("/api/garmin/connect", { email, password });
    setGarminStatus("Garmin connected.");
    await refreshAppState({ requestedView: "dashboard", replaceHistory: true, loadDashboardIfNeeded: true });
  } catch (error) {
    if (isUnauthorizedError(error)) {
      await handleUnauthorizedSession("Session expired. Sign in again.");
      return;
    }
    setGarminStatus(`Error: ${error.message}`);
    await refreshAppState({ requestedView: state.appView, replaceHistory: true, loadDashboardIfNeeded: false });
  }
}

function bindPlannedSessionButtons() {
  document.querySelectorAll(".plan-option-card").forEach((button) => {
    button.addEventListener("click", () => {
      const sessionType = button.dataset.sessionType;
      setStoredPlannedSessionType(sessionType);
      renderPlanSurface(state.planDashboard || {});
      renderDebug(state.planDashboard || state.activitiesDashboard || {}, state.currentForecast);
    });
  });
}

function planSyncMeta(sync) {
  if (!sync?.syncState) {
    return "No Sync Data Yet.";
  }
  const display = getSyncUiCopy(sync);
  if (sync.syncState === "syncing" || sync.syncState === "backfilling") {
    return display.metaText || "Sync In Progress";
  }
  if (display.metaText) {
    return display.metaText;
  }
  if (display.advisoryLines.length) {
    return display.advisoryLines[0];
  }
  const updatedAt = sync.lastFinishedSyncAt || sync.lastSuccessfulSyncAt;
  if (updatedAt) {
    return `Updated ${formatRelativeHours(updatedAt)}`;
  }
  if (sync.syncState === "never_synced") {
    return "Never synced";
  }
  if (sync.syncState === "blocked") {
    return "Reconnect Garmin";
  }
  if (sync.syncState === "error") {
    return "Check Sync tab";
  }
  return display.reasonLabel || syncReasonLabel(sync.statusReason);
}

function bindSyncActionButtons() {
  document.querySelectorAll(".sync-action-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.action;
      if (action === "update") {
        void startSyncRequest("/api/sync/update", null, "syncing");
      } else if (action === "backfill") {
        void startSyncRequest("/api/sync/backfill", { days: syncBackfillDays() }, "backfilling");
      } else if (action === "retry") {
        void startSyncRequest("/api/sync/update", null, "syncing");
      }
    });
  });
}

function bindSurfaceNav() {
  const surfaceNav = el("surfaceNav");
  if (!surfaceNav) {
    return;
  }

  surfaceNav.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveView(button.dataset.view);
    });
  });
}

function bindAdvancedToggle() {
  const toggle = el("advancedToggleBtn");
  if (!toggle) {
    return;
  }

  toggle.addEventListener("click", () => {
    state.advancedMode = !state.advancedMode;
    persistAdvancedModePreference();
    if (!debugSurfaceAllowed() && state.activeView === "debug") {
      state.activeView = "plan";
    }
    syncSurfaceUi();
  });

  window.addEventListener("hashchange", () => {
    if (state.appView === "dashboard") {
      setActiveView(requestedViewFromHash(), { syncHash: false });
    }
  });
}

function bindAppNavigation() {
  document.querySelectorAll("[data-app-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const targetView = button.dataset.appNav;
      if (targetView === "settings") {
        void activateAppView("settings", { replaceHistory: false, loadDashboardIfNeeded: false });
      } else if (targetView === "dashboard" && state.appState?.dashboardAccessible) {
        void activateAppView("dashboard", { replaceHistory: false, loadDashboardIfNeeded: true });
      }
    });
  });
}

function bindEvents() {
  bindSurfaceNav();
  bindAdvancedToggle();
  bindAppNavigation();
  hydrateRangeSelect(APP_CONFIG.rangeFilters || [7, 14, 28, 84, 365], state.rangeDays);
  syncTrainingFocusHelp(state.mode);

  document.querySelectorAll("[data-auth-action]").forEach((button) => {
    button.addEventListener("click", () => {
      void performAuthAction(button.dataset.authAction, button.dataset.authProvider);
    });
  });

  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.addEventListener("click", () => {
      void logout();
    });
  });
  const globalLogoutBtn = el("globalLogoutBtn");
  if (globalLogoutBtn) {
    globalLogoutBtn.addEventListener("click", () => {
      void logout();
    });
  }

  document.querySelectorAll("[data-garmin-submit]").forEach((button) => {
    button.addEventListener("click", () => {
      void submitGarminCredentials(button.dataset.garminSubmit);
    });
  });

  const syncSettingsBtn = el("syncSettingsBtn");
  if (syncSettingsBtn) {
    syncSettingsBtn.addEventListener("click", () => {
      void activateAppView("settings", { replaceHistory: false, loadDashboardIfNeeded: false });
    });
  }

  const settingsDashboardBtn = el("settingsDashboardBtn");
  if (settingsDashboardBtn) {
    settingsDashboardBtn.addEventListener("click", () => {
      if (state.appState?.dashboardAccessible) {
        void activateAppView("dashboard", { replaceHistory: false, loadDashboardIfNeeded: true });
      }
    });
  }

  const deleteAccountBtn = el("deleteAccountBtn");
  if (deleteAccountBtn) {
    deleteAccountBtn.addEventListener("click", () => {
      openAccountDeletionConfirmation();
    });
  }

  const cancelDeleteAccountBtn = el("cancelDeleteAccountBtn");
  if (cancelDeleteAccountBtn) {
    cancelDeleteAccountBtn.addEventListener("click", () => {
      if (!state.accountDeletionPending) {
        resetAccountDeletionUi();
      }
    });
  }

  const confirmDeleteAccountBtn = el("confirmDeleteAccountBtn");
  if (confirmDeleteAccountBtn) {
    confirmDeleteAccountBtn.addEventListener("click", () => {
      void deleteAccount();
    });
  }

  const deleteAccountConfirmInput = el("deleteAccountConfirmInput");
  if (deleteAccountConfirmInput) {
    deleteAccountConfirmInput.addEventListener("input", () => {
      if (!state.accountDeletionPending) {
        setAccountDeletionFeedback("This action cannot be undone.");
        syncAccountDeletionUi();
      }
    });
  }

  const rangeSelect = el("rangeSelect");
  if (rangeSelect) {
    rangeSelect.addEventListener("change", (event) => {
      state.rangeDays = Number(event.target.value);
      void loadDashboard();
    });
  }

  const modeSelect = el("modeSelect");
  if (modeSelect) {
    modeSelect.value = state.mode;
    modeSelect.addEventListener("change", (event) => {
      state.mode = event.target.value;
      syncTrainingFocusHelp(state.mode);
      void loadDashboard({ skipAutoSync: true });
    });
  }

  const activitiesCopyReviewPromptBtn = el("activitiesCopyReviewPromptBtn");
  if (activitiesCopyReviewPromptBtn) {
    activitiesCopyReviewPromptBtn.addEventListener("click", () => {
      void copyActivitiesReviewPrompt({
        state,
        setGarminStatus,
      });
    });
  }

  const activitiesImportReviewAnswerBtn = el("activitiesImportReviewAnswerBtn");
  if (activitiesImportReviewAnswerBtn) {
    activitiesImportReviewAnswerBtn.addEventListener("click", () => {
      void importActivitiesReviewAnswer({
        state,
        apiPost,
        setGarminStatus,
        reloadDashboard: loadDashboard,
      });
    });
  }

  el("copyPromptBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el("aiPrompt").value);
      el("copyPromptBtn").textContent = "Copied";
      setTimeout(() => {
        el("copyPromptBtn").textContent = "Copy Prompt";
      }, 1200);
    } catch (_error) {
      el("copyPromptBtn").textContent = "Error";
      setTimeout(() => {
        el("copyPromptBtn").textContent = "Copy Prompt";
      }, 1200);
    }
  });

  const retryAppStateBtn = el("retryAppStateBtn");
  if (retryAppStateBtn) {
    retryAppStateBtn.addEventListener("click", () => {
      void refreshAppState({ requestedView: requestedAppViewFromPath(), replaceHistory: true, loadDashboardIfNeeded: state.appView === "dashboard" });
    });
  }

  const errorLogoutBtn = el("errorLogoutBtn");
  if (errorLogoutBtn) {
    errorLogoutBtn.addEventListener("click", () => {
      void logout();
    });
  }

  window.addEventListener("popstate", () => {
    if (state.sessionRestorePending) {
      return;
    }
    state.activeView = resolveSurfaceView(requestedViewFromHash());
    void routeFromLocation();
  });
}

async function routeFromLocation() {
  if (state.sessionRestorePending) {
    return;
  }
  const requestedView = requestedAppViewFromPath();
  const resolvedView = resolveAllowedAppView(requestedView);
  const loadDashboardIfNeeded = resolvedView === "dashboard" && state.appView !== "dashboard";
  await activateAppView(resolvedView, { replaceHistory: true, loadDashboardIfNeeded });
}

async function restoreSession() {
  state.sessionRestorePending = true;
  try {
    if (!supabaseClient) {
      setLoggedOutState({
        authMessage: missingConfigMessage(),
        garminMessage: missingConfigMessage(),
      });
      return;
    }

    const callbackResult = await completeAuthCallbackIfNeeded();
    if (callbackResult.message) {
      applyCurrentSession(null);
      setLoggedOutState({
        authMessage: callbackResult.message,
        garminMessage: "Sign in to connect Garmin.",
      });
      return;
    }

    if (callbackResult.session?.access_token) {
      applyCurrentSession(callbackResult.session);
      await refreshAppState({
        requestedView: requestedAppViewFromPath(),
        replaceHistory: true,
        loadDashboardIfNeeded: true,
      });
      return;
    }

    const { data } = await supabaseClient.auth.getSession();
    applyCurrentSession(data?.session || null);

    if (state.currentSession?.access_token) {
      await refreshAppState({
        requestedView: requestedAppViewFromPath(),
        replaceHistory: normalizedPathname() === "/" || isAuthCallbackPath(),
        loadDashboardIfNeeded: true,
      });
      return;
    }

    if (isAuthCallbackPath()) {
      setLoggedOutState({
        authMessage: callbackResult.missingSessionMessage || callbackFailureMessage(),
        garminMessage: "Sign in to connect Garmin.",
      });
      return;
    }

    clearPendingAuthProvider();
    setLoggedOutState();
  } finally {
    state.sessionRestorePending = false;
  }
}
let hasLoadedInitialDashboard = false;

if (supabaseClient) {
  supabaseClient.auth.onAuthStateChange((_event, session) => {
    applyCurrentSession(session || null);
    
    // Explizite Behandlung verschiedener Events
    if (_event === "TOKEN_REFRESHED" || _event === "USER_UPDATED") {
      return;
    }

    // SIGNED_OUT setzt Flag zurück
    if (_event === "SIGNED_OUT") {
      hasLoadedInitialDashboard = false;
      clearPendingAuthProvider();
      setLoggedOutState();
      return;
    }

    // Verhindert redundanten Reload bei Tab-Fokus
    if (_event === "SIGNED_IN" && hasLoadedInitialDashboard) {
      return;
    }
    
    window.setTimeout(async () => {
      if (state.sessionRestorePending) {
        return;
      }
      if (state.currentSession?.access_token) {
        hasLoadedInitialDashboard = true;
        await refreshAppState({
          requestedView: requestedAppViewFromPath(),
          replaceHistory: true,
          loadDashboardIfNeeded: true,
        });
      }
    }, 0);
  });
}
window.state = state;
window.apiPost = apiPost;
window.renderDashboard = renderDashboard;
window.setGarminStatus = setGarminStatus;
async function bootstrapApplication() {
  state.activeView = resolveSurfaceView(requestedViewFromHash());
  bindEvents();
  resetAccountDeletionUi();
  setAuthUi(null);
  renderDashboard();
  renderSyncStatusPanel({}, "settingsSyncStatusPanel");

  if (isAuthCallbackPath()) {
    await restoreSession();
    return;
  }

  syncSurfaceUi({ syncHash: false });
  syncAppUi({ replaceHistory: false });
  await restoreSession();
}

function renderActivitiesReviewStatus(payload) {
  const container = el("activitiesReviewStatusCard");
  if (!container) {
    return;
  }

  const review = payload?.reviewStatus || null;
  if (!review || !review.reviewed) {
    container.innerHTML = `
      <div class="review-status-card review-status-card--empty">
        <div class="review-status-title">Review status</div>
        <div class="review-status-value muted-copy">Not reviewed yet.</div>
      </div>
    `;
    return;
  }

  const judgement = safeText(review.judgement || "-");
  const problemArea = safeText(review.problemArea || "-");
  const recommendedSession = safeText(review.recommendedSession || "-");
  const confidence = safeText(review.confidence || "-");

  container.innerHTML = `
    <div class="review-status-card">
      <div class="review-status-title">Review status</div>
      <div class="review-status-grid">
        <div class="review-status-row">
          <span class="review-status-label">Reviewed</span>
          <span class="review-status-value">Yes</span>
        </div>
        <div class="review-status-row">
          <span class="review-status-label">Judgement</span>
          <span class="review-status-value">${safeHtml(judgement)}</span>
        </div>
        <div class="review-status-row">
          <span class="review-status-label">Problem area</span>
          <span class="review-status-value">${safeHtml(problemArea)}</span>
        </div>
        <div class="review-status-row">
          <span class="review-status-label">Recommended</span>
          <span class="review-status-value">${safeHtml(recommendedSession)}</span>
        </div>
        <div class="review-status-row">
          <span class="review-status-label">Confidence</span>
          <span class="review-status-value">${safeHtml(confidence)}</span>
        </div>
      </div>
    </div>
  `;
}
void bootstrapApplication();
