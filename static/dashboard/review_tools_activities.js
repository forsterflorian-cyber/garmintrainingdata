(function () {
  function el(id) {
    return document.getElementById(id);
  }

  function currentActivitiesReviewPackage() {
    if (window.state?.activitiesDashboard?.review?.package) {
      return window.state.activitiesDashboard.review.package;
    }
    if (window.state?.dashboardData?.activities?.selectedDay?.review?.package) {
      return window.state.dashboardData.activities.selectedDay.review.package;
    }
    if (window.state?.planDashboard?.review?.package) {
      return window.state.planDashboard.review.package;
    }
    if (window.state?.dashboardData?.review?.package) {
      return window.state.dashboardData.review.package;
    }
    return null;
  }

  function currentActivitiesReviewPrompt() {
    if (window.state?.activitiesDashboard?.review?.prompt) {
      return window.state.activitiesDashboard.review.prompt;
    }
    if (window.state?.dashboardData?.activities?.selectedDay?.review?.prompt) {
      return window.state.dashboardData.activities.selectedDay.review.prompt;
    }
    if (window.state?.planDashboard?.review?.prompt) {
      return window.state.planDashboard.review.prompt;
    }
    if (window.state?.dashboardData?.review?.prompt) {
      return window.state.dashboardData.review.prompt;
    }
    return null;
  }

  function setStatus(message, tone) {
    if (typeof window.setGarminStatus === "function") {
      window.setGarminStatus(message, tone);
      return;
    }
    console.log(message);
  }

  async function copyActivitiesReviewPrompt() {
    const prompt = currentActivitiesReviewPrompt();
    if (!prompt) {
      setStatus("No review prompt available for the selected day.", "error");
      return;
    }

    try {
      await navigator.clipboard.writeText(prompt);
      setStatus("Activities review prompt copied.", "success");
    } catch (error) {
      console.error("copyActivitiesReviewPrompt failed", error);
      setStatus("Copy failed.", "error");
    }
  }

  async function importActivitiesReviewAnswer() {
    const raw = window.prompt("Paste ChatGPT JSON review");
    if (!raw) {
      return;
    }

    let review;
    try {
      review = JSON.parse(raw);
    } catch (error) {
      console.error("importActivitiesReviewAnswer invalid JSON", error);
      setStatus("Invalid JSON.", "error");
      return;
    }

    const reviewPackage = currentActivitiesReviewPackage();
    if (!reviewPackage) {
      setStatus("No review package available for the selected day.", "error");
      return;
    }

    try {
      if (typeof window.apiPost !== "function") {
        throw new Error("apiPost not available");
      }
      await window.apiPost("/api/dashboard/reviews", {
        case: reviewPackage,
        review,
      });
      setStatus("Activities review imported.", "success");
    } catch (error) {
      console.error("importActivitiesReviewAnswer failed", error);
      setStatus(error?.message || "Review import failed.", "error");
    }
  }

  function updateActivitiesReviewToolState() {
    const hasReview = Boolean(currentActivitiesReviewPrompt());
    const copyBtn = el("activitiesCopyReviewPromptBtn");
    const importBtn = el("activitiesImportReviewAnswerBtn");

    if (copyBtn) {
      copyBtn.disabled = !hasReview;
    }
    if (importBtn) {
      importBtn.disabled = !hasReview;
    }
  }

  function bindActivitiesReviewButtons() {
    const copyBtn = el("activitiesCopyReviewPromptBtn");
    const importBtn = el("activitiesImportReviewAnswerBtn");

    if (copyBtn && !copyBtn.dataset.reviewBound) {
      copyBtn.dataset.reviewBound = "true";
      copyBtn.addEventListener("click", copyActivitiesReviewPrompt);
    }

    if (importBtn && !importBtn.dataset.reviewBound) {
      importBtn.dataset.reviewBound = "true";
      importBtn.addEventListener("click", importActivitiesReviewAnswer);
    }

    updateActivitiesReviewToolState();
  }

  const originalRenderDashboard = window.renderDashboard;
  if (typeof originalRenderDashboard === "function") {
    window.renderDashboard = function patchedRenderDashboard(...args) {
      const result = originalRenderDashboard.apply(this, args);
      bindActivitiesReviewButtons();
      return result;
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindActivitiesReviewButtons);
  } else {
    bindActivitiesReviewButtons();
  }

  window.bindActivitiesReviewButtons = bindActivitiesReviewButtons;
  window.updateActivitiesReviewToolState = updateActivitiesReviewToolState;
})();