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
import { getPlannedSession, setPlannedSession } from "./lib/forecastUtils.js";
import { el, formatDateTime, formatNumber, formatRelativeHours, safeHtml, safeText } from "./lib/formatters.js";
import { computeNextDaysOutlook } from "./lib/outlookForecast.js";

const APP_CONFIG = window.__APP_CONFIG__ || {};
const SURFACE_VIEWS = ["plan", "analysis", "sync", "debug"];
const ADVANCED_MODE_KEY = "dashboard.advancedMode";

function loadAdvancedModePreference() {
  try {
    return window.localStorage.getItem(ADVANCED_MODE_KEY) === "true";
  } catch (_error) {
    return false;
  }
}

const state = {
  currentSession: null,
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
};

const supabaseClient = window.supabase && APP_CONFIG.supabaseUrl && APP_CONFIG.supabaseAnonKey
  ? window.supabase.createClient(APP_CONFIG.supabaseUrl, APP_CONFIG.supabaseAnonKey, {
      auth: {
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
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
  return missing.length ? `Missing Supabase Config: ${missing.join(", ")}` : "Missing Supabase Config.";
}

function authRedirectUrl() {
  const url = new URL(window.location.href);
  url.hash = "";
  url.search = "";
  return url.toString();
}

function currentUserId() {
  return state.currentSession?.user?.id || null;
}

function isSyncActive(syncState) {
  return syncState === "syncing" || syncState === "backfilling";
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

function syncLocationWithView(view) {
  if (view === "plan") {
    const nextUrl = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState(null, "", nextUrl);
    return;
  }
  if (window.location.hash !== `#${view}`) {
    window.location.hash = view;
  }
}

function syncSurfaceUi({ syncHash = true } = {}) {
  const activeView = resolveSurfaceView(state.activeView);
  state.activeView = activeView;

  const debugButton = el("debugNavBtn");
  if (debugButton) {
    debugButton.hidden = !debugSurfaceAllowed();
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
    advancedToggle.hidden = forcedOn;
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

function setControlsDisabled(disabled) {
  ["garminEmail", "garminPassword", "connectGarminBtn"].forEach((id) => {
    const node = el(id);
    if (node) {
      node.disabled = disabled;
    }
  });
}

function setAuthUi(user) {
  const loggedIn = Boolean(user);
  el("loginBtn").hidden = loggedIn;
  el("signupBtn").hidden = loggedIn;
  el("logoutBtn").hidden = !loggedIn;
  setControlsDisabled(!loggedIn);
}

async function getToken() {
  requireSupabaseClient();
  return state.currentSession?.access_token || null;
}

async function apiGet(url) {
  const token = await getToken();
  if (!token) {
    throw new Error("Sign in first.");
  }

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(json.error || `HTTP ${response.status}`);
  }
  return json;
}

async function apiPost(url, body = null) {
  const token = await getToken();
  if (!token) {
    throw new Error("Sign in first.");
  }

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
    throw new Error(json.error || `HTTP ${response.status}`);
  }
  return json;
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
    setGarminStatus(`Sync Status Error: ${error.message}`);
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
    if (isSyncActive(response.syncState)) {
      startSyncPolling();
    } else {
      stopSyncPolling();
      await loadDashboard({ skipAutoSync: true });
    }
  } catch (error) {
    setGarminStatus(`Sync Error: ${error.message}`);
    await refreshSyncStatus({ reloadDashboardOnTerminal: false });
  }
}

function maybeAutoSync() {
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
  try {
    const payload = await apiGet(dashboardUrl());
    state.dashboard = payload;
    state.selectedDate = payload?.date || state.selectedDate;
    state.syncStatus = payload?.sync || null;
    renderDashboard();

    if (payload?.account?.connected) {
      setGarminStatus(syncStatusSummary(payload.sync));
    } else {
      setGarminStatus("Garmin not connected.");
    }

    if (isSyncActive(payload?.sync?.syncState)) {
      startSyncPolling();
    } else {
      stopSyncPolling();
    }

    if (!skipAutoSync) {
      maybeAutoSync();
    }
  } catch (error) {
    if (String(error.message || "").toLowerCase().includes("sign in")) {
      setLoggedOutState();
      return;
    }
    setGarminStatus(`Error: ${error.message}`);
  }
}

function setLoggedOutState() {
  state.dashboard = null;
  state.selectedDate = null;
  state.syncStatus = null;
  state.autoSyncKey = null;
  stopSyncPolling();
  renderDashboard();
  setGarminStatus("Sign in to reconnect Garmin.");
}

async function login() {
  const email = el("loginEmail").value;
  const password = el("loginPassword").value;
  const { error } = await requireSupabaseClient().auth.signInWithPassword({ email, password });
  if (error) {
    alert(error.message);
    return;
  }
  setAuthStatus("Signed in. Loading session...");
}

async function signup() {
  const email = el("loginEmail").value;
  const password = el("loginPassword").value;
  const { error } = await requireSupabaseClient().auth.signUp({
    email,
    password,
    options: { emailRedirectTo: authRedirectUrl() },
  });
  if (error) {
    alert(error.message);
    return;
  }
  alert("Sign-up started. Confirm your email if required.");
}

async function logout() {
  if (supabaseClient) {
    await supabaseClient.auth.signOut();
  }
  state.currentSession = null;
  setAuthUi(null);
  setAuthStatus("Not Signed In");
  setLoggedOutState();
}

async function connectGarmin() {
  try {
    const email = el("garminEmail").value.trim();
    const password = el("garminPassword").value.trim();
    if (!email || !password) {
      setGarminStatus("Enter Garmin email and password.");
      return;
    }
    setGarminStatus("Checking Garmin credentials...");
    await apiPost("/api/garmin/connect", { email, password });
    setGarminStatus("Garmin connected.");
    await loadDashboard();
  } catch (error) {
    setGarminStatus(`Error: ${error.message}`);
    await refreshSyncStatus({ reloadDashboardOnTerminal: false });
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
    return `Last Updated ${formatRelativeHours(updatedAt)}`;
  }
  if (sync.syncState === "never_synced") {
    return "Never Synced";
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
    setActiveView(requestedViewFromHash(), { syncHash: false });
  });
}

function bindEvents() {
  bindSurfaceNav();
  bindAdvancedToggle();
  hydrateRangeSelect(APP_CONFIG.rangeFilters || [7, 14, 28, 84, 365], state.rangeDays);
  bindTabs();

  el("loginBtn").addEventListener("click", login);
  el("signupBtn").addEventListener("click", signup);
  el("logoutBtn").addEventListener("click", logout);
  el("connectGarminBtn").addEventListener("click", connectGarmin);

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
}

async function restoreSession() {
  if (!supabaseClient) {
    setAuthStatus(missingConfigMessage());
    setGarminStatus(missingConfigMessage());
    renderDashboard();
    return;
  }

  const { data } = await supabaseClient.auth.getSession();
  state.currentSession = data?.session || null;
  const user = state.currentSession?.user || null;
  setAuthUi(user);
  setAuthStatus(user ? `Signed in as ${user.email}` : "Not Signed In");

  if (state.currentSession?.access_token) {
    await loadDashboard();
  } else {
    setLoggedOutState();
  }
}

if (supabaseClient) {
  supabaseClient.auth.onAuthStateChange((_event, session) => {
    state.currentSession = session || null;
    const user = state.currentSession?.user || null;
    setAuthUi(user);
    setAuthStatus(user ? `Signed in as ${user.email}` : "Not Signed In");
    window.setTimeout(async () => {
      if (state.currentSession?.access_token) {
        await loadDashboard();
      } else {
        setLoggedOutState();
      }
    }, 0);
  });
}

state.activeView = resolveSurfaceView(requestedViewFromHash());
bindEvents();
syncSurfaceUi({ syncHash: false });
setAuthUi(null);
renderDashboard();
restoreSession();
