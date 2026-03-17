export function updateReviewToolState({ state, el }) {
  const planPrompt = state.planDashboard?.review?.prompt;
  const activitiesPrompt = state.activitiesDashboard?.review?.prompt;

  const copyPlanBtn = el("copyReviewPromptBtn");
  const importPlanBtn = el("importReviewAnswerBtn");
  const copyActivitiesBtn = el("activitiesCopyReviewPromptBtn");
  const importActivitiesBtn = el("activitiesImportReviewAnswerBtn");

  if (copyPlanBtn) copyPlanBtn.disabled = !planPrompt;
  if (importPlanBtn) importPlanBtn.disabled = !planPrompt;
  if (copyActivitiesBtn) copyActivitiesBtn.disabled = !activitiesPrompt;
  if (importActivitiesBtn) importActivitiesBtn.disabled = !activitiesPrompt;
}

export async function copyReviewPrompt({ state, setGarminStatus }) {
  const prompt = state.planDashboard?.review?.prompt;
  if (!prompt) {
    setGarminStatus("No review prompt available.");
    return;
  }

  try {
    await navigator.clipboard.writeText(prompt);
    setGarminStatus("Review prompt copied.");
  } catch (error) {
    console.error("copyReviewPrompt failed", error);
    setGarminStatus("Copy failed.");
  }
}

export async function importReviewAnswer({ state, apiPost, setGarminStatus }) {
  const raw = window.prompt("Paste ChatGPT JSON review");
  if (!raw) {
    return;
  }

  let review;
  try {
    review = JSON.parse(raw);
  } catch (error) {
    console.error("importReviewAnswer invalid JSON", error);
    setGarminStatus("Invalid JSON.");
    return;
  }

  const reviewPackage = state.planDashboard?.review?.package;
  if (!reviewPackage) {
    setGarminStatus("No review package available.");
    return;
  }

  try {
    await apiPost("/api/dashboard/reviews", {
      case: reviewPackage,
      review,
    });
    setGarminStatus(`Review imported for ${reviewPackage.date}.`);
  } catch (error) {
    console.error("importReviewAnswer failed", error);
    setGarminStatus(error?.message || "Review import failed.");
  }
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

export async function importActivitiesReviewAnswer({ state, apiPost, setGarminStatus }) {
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
    setGarminStatus(`Activities review imported for ${reviewPackage.date}.`);
  } catch (error) {
    console.error("importActivitiesReviewAnswer failed", error);
    setGarminStatus(error?.message || "Review import failed.");
  }
}