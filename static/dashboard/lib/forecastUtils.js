export function plannedSessionStorageKey(userId, date) {
  return `garmintrainingdata:planned:${userId || "anon"}:${date || "latest"}`;
}

export function getPlannedSession(userId, date) {
  try {
    return window.localStorage.getItem(plannedSessionStorageKey(userId, date));
  } catch (_error) {
    return null;
  }
}

export function setPlannedSession(userId, date, sessionType) {
  try {
    const key = plannedSessionStorageKey(userId, date);
    if (!sessionType) {
      window.localStorage.removeItem(key);
      return;
    }
    window.localStorage.setItem(key, sessionType);
  } catch (_error) {
    // Ignore storage failures and continue with in-memory behavior.
  }
}

export function applyPlannedSessionForecast(decision, plannedSessionType) {
  const impacts = decision?.tomorrowImpact?.bySessionType || {};
  if (plannedSessionType && impacts[plannedSessionType]) {
    return impacts[plannedSessionType];
  }

  const firstOption = (decision?.bestOptions || [])[0];
  if (firstOption && impacts[firstOption.type]) {
    return impacts[firstOption.type];
  }

  return {
    predictedScore: null,
    outlook: "select a session",
    tone: "neutral",
    text: "Select a planned session to project tomorrow.",
  };
}
