export function historyRowsFromPayload(payload) {
  if (!payload || !Array.isArray(payload.history?.rows)) {
    return [];
  }
  return payload.history.rows;
}

function dashboardUrlForDate({ mode, rangeDays, date = null }) {
  const params = new URLSearchParams({
    days: String(rangeDays),
    mode,
  });
  if (date) {
    params.set("date", date);
  }
  return `/api/dashboard?${params.toString()}`;
}

function resolveActivitiesDate(currentActivitiesDate, planPayload, manuallySelected) {
  const availableDays = historyRowsFromPayload(planPayload)
    .map((row) => (typeof row?.date === "string" && row.date ? row.date : null))
    .filter(Boolean);

  const todayDate =
    planPayload?.date ||
    planPayload?.detail?.activeDate ||
    null;

  if (manuallySelected && currentActivitiesDate && availableDays.includes(currentActivitiesDate)) {
    return currentActivitiesDate;
  }

  if (todayDate && availableDays.includes(todayDate)) {
    return todayDate;
  }

  return availableDays[availableDays.length - 1] || todayDate || null;
}

export async function loadDashboardData({
  state,
  apiGet,
  setDashboardLoadingState,
  setGarminStatus,
  renderDashboard,
  renderSyncStatusPanel,
  maybeAutoSync,
  skipAutoSync = false,
}) {
  if (!state.currentSession?.access_token || !state.appState?.dashboardAccessible) {
    return null;
  }

  const requestId = ++state.dashboardLoadRequestId;
  setDashboardLoadingState(true);

  try {
    const planPayload = await apiGet(
      dashboardUrlForDate({
        mode: state.mode,
        rangeDays: state.rangeDays,
        date: state.todayDate,
      }),
    );

    if (requestId !== state.dashboardLoadRequestId) {
      return null;
    }

    const resolvedTodayDate = planPayload?.date || state.todayDate || null;
    const resolvedActivitiesDate = resolveActivitiesDate(state.activitiesDate, planPayload, state.activitiesDateManuallySelected);

    let activitiesPayload = planPayload;

    if (resolvedActivitiesDate && resolvedActivitiesDate !== resolvedTodayDate) {
      activitiesPayload = await apiGet(
        dashboardUrlForDate({
          mode: state.mode,
          rangeDays: state.rangeDays,
          date: resolvedActivitiesDate,
        }),
      );

      if (requestId !== state.dashboardLoadRequestId) {
        return null;
      }
    }

    state.planDashboard = planPayload;
    state.activitiesDashboard = activitiesPayload;
    state.todayDate = resolvedTodayDate;
    state.activitiesDate = resolvedActivitiesDate || resolvedTodayDate || null;
    state.syncStatus = planPayload?.sync || null;

    renderDashboard();
    renderSyncStatusPanel(state.syncStatus || {}, "settingsSyncStatusPanel");

    if (!skipAutoSync) {
      maybeAutoSync();
    }

    return {
      planDashboard: state.planDashboard,
      activitiesDashboard: state.activitiesDashboard,
    };
  } catch (error) {
    console.error("loadDashboardData failed", error);
    setGarminStatus(error?.message || "Dashboard load failed.");
    throw error;
  } finally {
    if (requestId === state.dashboardLoadRequestId) {
      setDashboardLoadingState(false);
    }
  }
}