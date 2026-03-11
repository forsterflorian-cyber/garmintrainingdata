import { renderAvoidTodayPanel } from "./components/decision/AvoidTodayPanel.js";
import { renderBestOptionsPanel } from "./components/decision/BestOptionsPanel.js";
import { renderNextDaysOutlookPanel } from "./components/decision/NextDaysOutlookPanel.js";
import { renderTomorrowImpactPanel } from "./components/decision/TomorrowImpactPanel.js";
import { renderTrainingDecisionCard } from "./components/decision/TrainingDecisionCard.js";
import { renderWhyRecommendationPanel } from "./components/decision/WhyRecommendationPanel.js";
import { setAuthStatus, setGarminStatus } from "./components/layout/DashboardHeader.js";
import { hydrateRangeSelect } from "./components/layout/FocusFilters.js";
import { renderBaselineComparisonCard } from "./components/metrics/BaselineComparisonCard.js";
import { renderLoadTrendCard } from "./components/trends/LoadTrendCard.js";
import { renderReadinessTrendCard } from "./components/trends/ReadinessTrendCard.js";
import { renderSyncActionButtons } from "./components/sync/SyncActionButtons.js";
import { renderSyncStatusBadge, syncLabelForState } from "./components/sync/SyncStatusBadge.js";
import { renderSyncStatusPanel, syncReasonLabel } from "./components/sync/SyncStatusPanel.js";
import { clearPlannedSessionsForUser, getPlannedSession, setPlannedSession } from "./lib/forecastUtils.js";
import { el, formatDateTime, formatNumber, formatRelativeHours, safeHtml, safeText } from "./lib/formatters.js";
import { computeNextDaysOutlook } from "./lib/outlookForecast.js";

const APP_CONFIG = window.__APP_CONFIG__ || {};
const SURFACE_VIEWS = ["plan", "analysis", "sync", "debug"];
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
  dashboard: null,
  selectedDate: null,
  rangeDays: APP_CONFIG.defaultRangeDays || 28,
  mode: "hybrid",
  activeView: "plan",
  activeTab: "trends",
  advancedMode: loadAdvancedModePreference(),
  syncStatus: null,
  currentForecast: null,
  syncPollTimer: null,
  syncPollInFlight: false,
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

function normalizedPathname(pathname = window.location.pathname) {
  if (!pathname || pathname === "/") {
    return "/";
  }
  return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
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

function requestedViewFromHash() {
  const raw = window.location.hash.replace("#", "").trim().toLowerCase();
  return SURFACE_VIEWS.includes(raw) ? raw : "plan";
}

function resolveSurfaceView(view) {
  if (!SURFACE_VIEWS.includes(view)) {
    return "plan";
  }
  if (view === "debug" && !debugSurfaceAllowed()) {
    return "plan";
  }
  return view;
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

async function apiGet(url) {
  const token = await getToken();
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw buildApiError(response, json);
  }
  return json;
}

async function apiPost(url, body = null) {
  const token = await getToken();
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : null,
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw buildApiError(response, json);
  }
  return json;
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

function dashboardUrl() {
  const params = new URLSearchParams({
    days: String(state.rangeDays),
    mode: state.mode,
  });
  if (state.selectedDate) {
    params.set("date", state.selectedDate);
  }
  return `/api/dashboard?${params.toString()}`;
}

function currentBestOptions() {
  return state.dashboard?.decision?.bestOptions || [];
}

function getStoredPlannedSession() {
  return getPlannedSession(currentUserId(), state.dashboard?.date);
}

function validPlannedSessionType() {
  const plannedType = getStoredPlannedSession();
  if (plannedType && currentBestOptions().some((option) => option.type === plannedType)) {
    return plannedType;
  }
  return currentBestOptions()[0]?.type || null;
}

function setStoredPlannedSessionType(sessionType) {
  setPlannedSession(currentUserId(), state.dashboard?.date, sessionType);
}

function syncStatusSummary(sync) {
  if (!sync?.syncState) {
    return "No Sync Data Yet.";
  }
  if (sync.lastErrorMessage) {
    return sync.lastErrorMessage;
  }
  if (sync.lastSuccessfulSyncAt) {
    return `Last Success ${formatDateTime(sync.lastSuccessfulSyncAt)}`;
  }
  if (sync.syncState === "never_synced") {
    return "No Successful Sync Yet.";
  }
  return sync.statusReason ? syncReasonLabel(sync.statusReason) : "No Sync Detail.";
}

function renderSyncUi(sync = state.syncStatus) {
  renderSyncStatusBadge(sync || {});
  renderSyncStatusPanel(sync || {});
  renderSyncActionButtons(sync || {});
  renderSyncStatusPanel(sync || {}, "settingsSyncStatusPanel");
  bindSyncActionButtons();

  if (el("planSyncMeta")) {
    el("planSyncMeta").textContent = planSyncMeta(sync);
  }

  if (el("snapshotSyncStatus")) {
    el("snapshotSyncStatus").textContent = safeText(syncLabelForState(sync?.syncState || "unknown"));
  }
  if (el("snapshotSyncMeta")) {
    el("snapshotSyncMeta").textContent = syncStatusSummary(sync);
  }
}

function renderDecisionPanels(payload) {
  renderTrainingDecisionCard({ payload });
  renderWhyRecommendationPanel(payload?.decision?.why || []);
  renderAvoidTodayPanel(payload?.decision?.avoid || []);

  const selectedType = validPlannedSessionType();
  if (selectedType && selectedType !== getStoredPlannedSession()) {
    setStoredPlannedSessionType(selectedType);
  }
  renderBestOptionsPanel(currentBestOptions(), { selectedType });
  bindPlannedSessionButtons();

  const selectedOption = currentBestOptions().find((option) => option.type === selectedType) || null;
  const outlook = computeNextDaysOutlook({
    currentDecision: payload?.decision,
    currentMetrics: payload?.today,
    currentLoad: payload?.load,
    currentComparisons: payload?.comparisons,
    baseline: payload?.baseline,
    selectedSession: selectedOption,
    currentDate: payload?.today?.recommendationDay || payload?.date,
    mode: payload?.mode,
    days: 4,
  });

  state.currentForecast = outlook;
  renderTomorrowImpactPanel({
    impact: outlook?.tomorrowImpact,
    plannedOptionLabel: selectedOption?.label || null,
  });
  renderNextDaysOutlookPanel(outlook);
}

function renderSummary(payload) {
  el("summaryAverageReadiness").textContent = formatNumber(payload?.summary?.avgReadiness, 1);
  el("summaryAverageLoad").textContent = formatNumber(payload?.summary?.avgLoad, 1);
  el("snapshotFocusDate").textContent = safeText(payload?.date);
  el("snapshotWindow").textContent = `${safeText(payload?.filters?.periodDays)} Days`;
  el("snapshotRatio").textContent = formatNumber(payload?.load?.ratio7to28, 2);
  el("snapshotStress").textContent = safeText(payload?.decision?.loadTolerance);
  el("snapshotModelRecommendation").textContent = safeText(payload?.decision?.primaryRecommendation);
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

function renderHeatmap(rows, activeDate) {
  const target = el("loadHeatmap");
  if (!rows.length) {
    target.innerHTML = "";
    return;
  }

  const maxLoad = Math.max(...rows.map((row) => Number(row.loadDay || 0)), 1);
  target.innerHTML = rows.map((row) => {
    const strength = Math.min(1, Number(row.loadDay || 0) / maxLoad);
    const activeClass = row.date === activeDate ? "is-active" : "";
    return `<div class="heat-cell ${activeClass}" data-label="${row.date.slice(5)}" style="--strength:${strength.toFixed(3)}" title="${row.date}: ${formatNumber(row.loadDay, 1)}"></div>`;
  }).join("");
}

function renderHistoryTable(rows, activeDate) {
  const target = el("historyTable");
  if (!rows.length) {
    target.innerHTML = '<tr><td colspan="5" class="muted-copy">No History In Range.</td></tr>';
    return;
  }

  target.innerHTML = rows.slice().reverse().map((row) => `
    <tr class="history-row ${row.date === activeDate ? "is-active" : ""}" data-day="${safeHtml(row.date)}">
      <td>${safeHtml(row.date)}</td>
      <td>${formatNumber(row.readiness, 0)}</td>
      <td>${formatNumber(row.loadDay, 1)}</td>
      <td>${formatNumber(row.ratio7to28, 2)}</td>
      <td>${safeHtml(row.primaryRecommendation)}</td>
    </tr>
  `).join("");

  target.querySelectorAll(".history-row").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedDate = row.dataset.day;
      void loadDashboard({ skipAutoSync: true });
    });
  });
}

function renderActivities(payload) {
  const activities = payload?.detail?.activities || [];
  el("activityHeadline").textContent = payload?.date ? `Activities On ${payload.date}` : "Focus Day Activities";
  if (!activities.length) {
    el("activityList").innerHTML = '<div class="muted-copy">No Activities For This Day.</div>';
    return;
  }

  el("activityList").innerHTML = activities.map((activity) => `
    <article class="activity-card">
      <div class="relative-head">
        <div>
          <div class="relative-title">${safeHtml(activity.name || activity.type_key || "Activity")}</div>
          <div class="muted-copy">${safeHtml(activity.type_key || "-")} | ${safeHtml(activity.start_local || "-")}</div>
        </div>
        <div class="relative-value">${formatNumber(activity.duration_min, 0)} min</div>
      </div>
      <div class="activity-chips">
        <span class="chip">Avg HR ${formatNumber(activity.avg_hr, 0)}</span>
        <span class="chip">Max HR ${formatNumber(activity.max_hr, 0)}</span>
        <span class="chip">TE ${formatNumber(activity.aerobic_te, 1)} / ${formatNumber(activity.anaerobic_te, 1)}</span>
        <span class="chip">Load ${formatNumber(activity.training_load, 1)}</span>
      </div>
    </article>
  `).join("");
}

function renderModeUnits(payload) {
  const units = (payload?.detail?.legacyUnits || {})[state.mode] || (payload?.detail?.legacyUnits || {}).hybrid || [];
  el("unitIntro").textContent = `Mode: ${state.mode}.`;
  if (!units.length) {
    el("unitCards").innerHTML = '<div class="muted-copy">No Model Outputs Available.</div>';
    return;
  }

  el("unitCards").innerHTML = units.map((unit, index) => `
    <article class="unit-card">
      <p class="eyebrow">Option ${index + 1}</p>
      <div>${safeHtml(unit)}</div>
    </article>
  `).join("");
}

function renderPrompt(payload) {
  const promptField = el("aiPrompt");
  if (promptField) {
    promptField.value = payload?.detail?.aiPrompt || "";
  }
}

function renderDashboard() {
  const payload = state.dashboard;
  renderSyncUi(payload?.sync || state.syncStatus);

  if (!payload || !payload.history?.rows?.length) {
    state.currentForecast = null;
    renderTrainingDecisionCard({ payload: payload || {} });
    renderWhyRecommendationPanel([]);
    renderAvoidTodayPanel([]);
    renderBestOptionsPanel([]);
    renderTomorrowImpactPanel({ impact: null, plannedOptionLabel: null });
    renderNextDaysOutlookPanel(null);
    renderBaselineComparisonCard([]);
    renderReadinessTrendCard([], null);
    renderLoadTrendCard([], null);
    renderHeatmap([], null);
    renderHistoryTable([], null);
    renderActivities({});
    renderModeUnits({});
    renderPrompt({});
    renderSummary(payload || {});
    renderDebug(payload || {}, state.currentForecast);
    return;
  }

  renderDecisionPanels(payload);
  renderBaselineComparisonCard(payload.baselineBars || []);
  renderReadinessTrendCard(payload.trends?.readinessSeries || [], payload.date);
  renderLoadTrendCard(payload.trends?.loadSeries || [], payload.date);
  renderHeatmap(payload.history.rows || [], payload.date);
  renderHistoryTable(payload.history.rows || [], payload.date);
  renderActivities(payload);
  renderModeUnits(payload);
  renderPrompt(payload);
  renderSummary(payload);
  renderDebug(payload, state.currentForecast);
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
  const sync = state.dashboard?.sync;
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

async function loadDashboard({ skipAutoSync = false } = {}) {
  if (!state.currentSession?.access_token || !state.appState?.dashboardAccessible) {
    return;
  }

  try {
    const payload = await apiGet(dashboardUrl());
    state.dashboard = payload;
    state.selectedDate = payload?.date || state.selectedDate;
    state.syncStatus = payload?.sync || null;
    renderDashboard();
    renderSyncStatusPanel(state.syncStatus || {}, "settingsSyncStatusPanel");

    if (payload?.sync?.syncState === "blocked") {
      await refreshAppState({ requestedView: "settings", replaceHistory: true, loadDashboardIfNeeded: false });
      return;
    }

    setGarminStatus(syncStatusSummary(payload.sync));

    if (isSyncActive(payload?.sync?.syncState)) {
      startSyncPolling();
    } else {
      stopSyncPolling();
    }

    if (!skipAutoSync) {
      maybeAutoSync();
    }
  } catch (error) {
    if (isUnauthorizedError(error)) {
      await handleUnauthorizedSession("Session expired. Sign in again.");
      return;
    }
    setGarminStatus(`Error: ${error.message}`);
  }
}

function setLoggedOutState({ authMessage = "Not signed in", garminMessage = "Sign in to connect Garmin." } = {}) {
  state.appState = null;
  state.appStateError = null;
  state.appView = "auth";
  state.dashboard = null;
  state.selectedDate = null;
  state.syncStatus = null;
  state.autoSyncKey = null;
  stopSyncPolling();
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
      renderDecisionPanels(state.dashboard || {});
      renderDebug(state.dashboard || {}, state.currentForecast);
    });
  });
}

function planSyncMeta(sync) {
  if (!sync?.syncState) {
    return "No Sync Data Yet.";
  }
  if (sync.syncState === "syncing" || sync.syncState === "backfilling") {
    return "Sync In Progress";
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
    return "Check Sync Surface";
  }
  return syncReasonLabel(sync.statusReason);
}

function bindSyncActionButtons() {
  document.querySelectorAll(".sync-action-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.action;
      if (action === "update") {
        void startSyncRequest("/api/sync/update", null, "syncing");
      } else if (action === "backfill") {
        void startSyncRequest("/api/sync/backfill", { days: 14 }, "backfilling");
      } else if (action === "retry") {
        void startSyncRequest("/api/sync/update", null, "syncing");
      }
    });
  });
}

function bindTabs() {
  const tabBar = el("tabBar");
  if (!tabBar) {
    return;
  }

  tabBar.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      tabBar.querySelectorAll(".tab-btn").forEach((node) => {
        node.classList.toggle("is-active", node === button);
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.panel === state.activeTab);
      });
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
  bindTabs();

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

  el("rangeSelect").addEventListener("change", (event) => {
    state.rangeDays = Number(event.target.value);
    void loadDashboard();
  });

  el("modeSelect").addEventListener("change", (event) => {
    state.mode = event.target.value;
    void loadDashboard({ skipAutoSync: true });
  });

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

if (supabaseClient) {
  supabaseClient.auth.onAuthStateChange((_event, session) => {
    applyCurrentSession(session || null);
    window.setTimeout(async () => {
      if (state.sessionRestorePending) {
        return;
      }
      if (state.currentSession?.access_token) {
        await refreshAppState({
          requestedView: requestedAppViewFromPath(),
          replaceHistory: true,
          loadDashboardIfNeeded: true,
        });
      } else {
        clearPendingAuthProvider();
        setLoggedOutState();
      }
    }, 0);
  });
}

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

void bootstrapApplication();
