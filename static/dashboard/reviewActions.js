export function updateReviewToolState({ state, el }) {
  const activitiesPrompt = state.activitiesDashboard?.review?.prompt;

  const copyActivitiesBtn = el("activitiesCopyReviewPromptBtn");
  const importActivitiesBtn = el("activitiesImportReviewAnswerBtn");

  if (copyActivitiesBtn) copyActivitiesBtn.disabled = !activitiesPrompt;
  if (importActivitiesBtn) importActivitiesBtn.disabled = !activitiesPrompt;
}

export async function copyActivitiesReviewPrompt({ state, setGarminStatus }) {
  const prompt = state.activitiesDashboard?.review?.prompt;
  if (!prompt) {
    setGarminStatus("No review prompt available for the selected day.");
    return;
  }

  try {
    await navigator.clipboard.writeText(prompt);
    setGarminStatus("Activities review prompt copied.");
  } catch (error) {
    console.error("copyActivitiesReviewPrompt failed", error);
    setGarminStatus("Copy failed.");
  }
}

export async function importActivitiesReviewAnswer({
  state,
  apiPost,
  setGarminStatus,
  reloadDashboard,
}) {
  const raw = window.prompt("Paste ChatGPT JSON review");
  if (!raw) {
    return;
  }

  let review;
  try {
    review = JSON.parse(raw);
  } catch (error) {
    console.error("importActivitiesReviewAnswer invalid JSON", error);
    setGarminStatus("Invalid JSON.");
    return;
  }

  const reviewPackage = state.activitiesDashboard?.review?.package;
  if (!reviewPackage) {
    setGarminStatus("No review package available for the selected day.");
    return;
  }

  try {
    await apiPost("/api/dashboard/reviews", {
      case: reviewPackage,
      review,
    });

    if (reloadDashboard) {
      await reloadDashboard({ skipAutoSync: true });
    }

    setGarminStatus(`Activities review imported for ${reviewPackage.date}.`);
  } catch (error) {
    console.error("importActivitiesReviewAnswer failed", error);
    setGarminStatus(error?.message || "Review import failed.");
  }
}