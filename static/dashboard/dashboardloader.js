export function historyRowsFromPayload(payload) {
  if (!payload || !Array.isArray(payload.history)) {
    return [];
  }
  return payload.history;
}

function buildDashboardUrl({ mode, rangeDays, selectedDate }) {
  const params = new URLSearchParams();
  if (mode) params.set("mode", mode);
  if (rangeDays) params.set("days", String(rangeDays));
  if (selectedDate) params.set("date", selectedDate);
  const query = params.toString();
  return `/api/dashboard${query ? `?${query}` : ""}`;
}

async function fetchDashboardPayload({ apiGet, mode, rangeDays, selectedDate }) {
  const url = buildDashboardUrl({ mode, rangeDays, selectedDate });
  return apiGet(url);
}

export async function loadDashboardData({
  state,
  apiGet,
  setDashboardLoadingState,
  setGarminStatus,
}) {
  const mode = state.mode;
  const rangeDays = state.rangeDays;
  const selectedActivitiesDate = state.activitiesDate;

  setDashboardLoadingState(true);

  try {
    const planPayload = await fetchDashboardPayload({
      apiGet,
      mode,
      rangeDays,
      selectedDate: null,
    });

    state.planDashboard = planPayload;
    state.todayDate = planPayload?.date || planPayload?.detail?.activeDate || null;

    const effectiveActivitiesDate =
      selectedActivitiesDate ||
      state.todayDate ||
      null;

    state.activitiesDate = effectiveActivitiesDate;

    if (
      effectiveActivitiesDate &&
      effectiveActivitiesDate !== state.todayDate
    ) {
      state.activitiesDashboard = await fetchDashboardPayload({
        apiGet,
        mode,
        rangeDays,
        selectedDate: effectiveActivitiesDate,
      });
    } else {
      state.activitiesDashboard = planPayload;
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
    setDashboardLoadingState(false);
  }
}