/**
 * User Profile Form Component
 * Ermöglicht Benutzern ihre Trainings-Parameter zu verwalten
 */

import { el, safeHtml, safeText } from "../../lib/formatters.js";

/**
 * Rendert das User-Profil Formular
 */
export function renderUserProfileForm(userProfile, onSave, onEstimate) {
  const container = el("userProfileForm");
  if (!container) {
    return;
  }

  const profile = userProfile || {};

  container.innerHTML = `
    <div class="user-profile-form">
      <div class="user-profile-header">
        <h3>Training Profile</h3>
        <p class="muted-copy">Set your personal training metrics for advanced analysis.</p>
      </div>

      <div class="user-profile-actions">
        <button id="estimateMetricsBtn" class="btn btn-secondary" type="button">
          <span>Estimate from History</span>
        </button>
      </div>

      <form id="profileForm" class="user-profile-form-fields">
        <fieldset class="profile-section">
          <legend>Personal Data</legend>
          <div class="profile-grid">
            <label class="profile-field">
              <span>Age</span>
              <input type="number" id="profileAge" name="age" value="${profile.age || ''}" min="1" max="120" placeholder="30">
            </label>
            <label class="profile-field">
              <span>Weight (kg)</span>
              <input type="number" id="profileWeight" name="weight_kg" value="${profile.weight_kg || ''}" min="20" max="500" step="0.1" placeholder="75.0">
            </label>
            <label class="profile-field">
              <span>Height (cm)</span>
              <input type="number" id="profileHeight" name="height_cm" value="${profile.height_cm || ''}" min="50" max="300" step="0.1" placeholder="180.0">
            </label>
            <label class="profile-field">
              <span>Gender</span>
              <select id="profileGender" name="gender">
                <option value="">Select...</option>
                <option value="male" ${profile.gender === 'male' ? 'selected' : ''}>Male</option>
                <option value="female" ${profile.gender === 'female' ? 'selected' : ''}>Female</option>
                <option value="other" ${profile.gender === 'other' ? 'selected' : ''}>Other</option>
              </select>
            </label>
          </div>
        </fieldset>

        <fieldset class="profile-section">
          <legend>Heart Rate</legend>
          <div class="profile-grid">
            <label class="profile-field">
              <span>Max HR (bpm)</span>
              <input type="number" id="profileMaxHr" name="max_hr" value="${profile.max_hr || ''}" min="100" max="250" placeholder="190">
            </label>
            <label class="profile-field">
              <span>Resting HR (bpm)</span>
              <input type="number" id="profileRestingHr" name="resting_hr" value="${profile.resting_hr || ''}" min="30" max="120" placeholder="60">
            </label>
            <label class="profile-field">
              <span>LTHR (bpm)</span>
              <input type="number" id="profileLthr" name="lthr" value="${profile.lthr || ''}" min="100" max="250" placeholder="170">
              <small class="field-hint">Lactate Threshold Heart Rate</small>
            </label>
          </div>
        </fieldset>

        <fieldset class="profile-section">
          <legend>Power (Cycling)</legend>
          <div class="profile-grid">
            <label class="profile-field">
              <span>FTP (watt)</span>
              <input type="number" id="profileFtp" name="ftp" value="${profile.ftp || ''}" min="50" max="2000" step="0.1" placeholder="250.0">
              <small class="field-hint">Functional Threshold Power</small>
            </label>
            <label class="profile-field">
              <span>Critical Power (watt)</span>
              <input type="number" id="profileCriticalPower" name="critical_power" value="${profile.critical_power || ''}" min="50" max="2000" step="0.1" placeholder="260.0">
            </label>
          </div>
        </fieldset>

        <fieldset class="profile-section">
          <legend>Pace (Running)</legend>
          <div class="profile-grid">
            <label class="profile-field">
              <span>Critical Pace (min/km)</span>
              <input type="number" id="profileCriticalPace" name="critical_pace" value="${profile.critical_pace || ''}" min="2.0" max="20.0" step="0.01" placeholder="4.50">
              <small class="field-hint">Your threshold pace</small>
            </label>
            <label class="profile-field">
              <span>VDOT</span>
              <input type="number" id="profileVdot" name="vdot" value="${profile.vdot || ''}" min="20" max="100" step="0.1" placeholder="50.0">
              <small class="field-hint">Jack Daniels' VDOT Score</small>
            </label>
          </div>
        </fieldset>

        <fieldset class="profile-section">
          <legend>Training Preferences</legend>
          <div class="profile-grid">
            <label class="profile-field">
              <span>Sport Focus</span>
              <select id="profileSportFocus" name="sport_focus">
                <option value="">Select...</option>
                <option value="run" ${profile.sport_focus === 'run' ? 'selected' : ''}>Run</option>
                <option value="bike" ${profile.sport_focus === 'bike' ? 'selected' : ''}>Bike</option>
                <option value="strength" ${profile.sport_focus === 'strength' ? 'selected' : ''}>Strength</option>
                <option value="hybrid" ${profile.sport_focus === 'hybrid' ? 'selected' : ''}>Hybrid</option>
              </select>
            </label>
            <label class="profile-field">
              <span>Weekly Volume (min)</span>
              <input type="number" id="profileWeeklyVolume" name="weekly_volume_target" value="${profile.weekly_volume_target || ''}" min="0" max="10000" placeholder="420">
            </label>
          </div>
        </fieldset>

        <div class="profile-form-actions">
          <button type="submit" class="btn btn-primary">Save Profile</button>
          <button type="button" id="deleteProfileBtn" class="btn btn-danger">Delete Profile</button>
        </div>
      </form>

      <div id="estimationResults"></div>
      <div id="profileFeedback" class="profile-feedback" hidden></div>
    </div>
  `;

  const form = el("profileForm");
  const estimateBtn = el("estimateMetricsBtn");
  const deleteBtn = el("deleteProfileBtn");

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const data = {};
      
      for (const [key, value] of formData.entries()) {
        if (value !== '') {
          const numFields = ['age', 'weight_kg', 'height_cm', 'max_hr', 'resting_hr', 'lthr', 'ftp', 'critical_power', 'critical_pace', 'vdot', 'weekly_volume_target'];
          data[key] = numFields.includes(key) ? parseFloat(value) : value;
        }
      }
      
      onSave(data);
    });
  }

  if (estimateBtn) {
    estimateBtn.addEventListener("click", () => onEstimate());
  }

  if (deleteBtn) {
    deleteBtn.addEventListener("click", () => {
      if (confirm("Delete your profile?")) {
        onSave(null, true);
      }
    });
  }
}

export function showEstimationResults(estimated, onApply) {
  const container = el("estimationResults");
  if (!container || !estimated || Object.keys(estimated).length === 0) {
    return;
  }

  let html = '<div class="estimation-results"><h4>Estimated Metrics</h4><div class="estimation-grid">';
  
  if (estimated.ftp) html += `<div class="estimation-item"><span>FTP</span><strong>${estimated.ftp}W</strong></div>`;
  if (estimated.critical_pace) html += `<div class="estimation-item"><span>Critical Pace</span><strong>${estimated.critical_pace} min/km</strong></div>`;
  if (estimated.lthr) html += `<div class="estimation-item"><span>LTHR</span><strong>${estimated.lthr} bpm</strong></div>`;
  
  html += '</div><button id="applyEstimationBtn" class="btn btn-primary">Apply Estimates</button></div>';
  container.innerHTML = html;

  el("applyEstimationBtn")?.addEventListener("click", () => onApply(estimated));
}

export function showProfileFeedback(message, type = "info") {
  const feedback = el("profileFeedback");
  if (!feedback) return;
  
  feedback.className = `profile-feedback profile-feedback--${type}`;
  feedback.textContent = message;
  feedback.hidden = false;
  
  setTimeout(() => { feedback.hidden = true; }, 5000);
}