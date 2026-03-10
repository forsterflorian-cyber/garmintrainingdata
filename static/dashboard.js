const APP_CONFIG = window.__APP_CONFIG__ || {};
const state = {
  currentSession: null,
  dashboard: null,
  selectedDate: null,
  rangeDays: APP_CONFIG.defaultRangeDays || 28,
  mode: "hybrid",
  activeTab: "trends",
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

function el(id) {
  return document.getElementById(id);
}

function safeText(value, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function safeHtml(value, fallback = "-") {
  return safeText(value, fallback)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}

function formatSigned(value, digits = 1, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(digits)}${suffix}`;
}

function parseDay(day) {
  return new Date(`${day}T00:00:00`);
}

function dateDistanceFromLatest(day, latestDay) {
  const diffMs = parseDay(latestDay).getTime() - parseDay(day).getTime();
  return Math.floor(diffMs / 86400000);
}

function rangeLabel(days) {
  return days >= 365 ? "1 Jahr" : `${days} Tage`;
}

function scoreTone(score) {
  if (score === null || score === undefined) return "neutral";
  if (score >= 75) return "positive";
  if (score >= 55) return "warning";
  return "critical";
}

function ratioTone(ratio) {
  if (ratio === null || ratio === undefined) return "neutral";
  if (ratio > 1.5 || ratio < 0.8) return "critical";
  if (ratio > 1.3) return "warning";
  return "positive";
}

function syncTone(status) {
  if (status === "ok" || status === "connected") return "positive";
  if (status === "error") return "critical";
  return "warning";
}

function missingConfigMessage() {
  const missing = APP_CONFIG.missingPublicConfig || [];
  return missing.length ? `Supabase Konfiguration fehlt: ${missing.join(", ")}` : "Supabase Konfiguration fehlt.";
}

function requireSupabaseClient() {
  if (!supabaseClient) {
    throw new Error(missingConfigMessage());
  }
  return supabaseClient;
}

function authRedirectUrl() {
  const url = new URL(window.location.href);
  url.hash = "";
  url.search = "";
  return url.toString();
}

function setControlsDisabled(disabled) {
  ["garminEmail", "garminPassword", "connectGarminBtn", "updateBtn", "backfillBtn"].forEach((id) => {
    const node = el(id);
    if (node) node.disabled = disabled;
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
    throw new Error("Bitte zuerst einloggen.");
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
    throw new Error("Bitte zuerst einloggen.");
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

function hydrateRangeSelect() {
  const select = el("rangeSelect");
  select.innerHTML = "";
  (APP_CONFIG.rangeFilters || [7, 14, 28, 84, 365]).forEach((days) => {
    const option = document.createElement("option");
    option.value = String(days);
    option.textContent = rangeLabel(days);
    if (Number(days) === Number(state.rangeDays)) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

function clearDashboard() {
  state.dashboard = null;
  state.selectedDate = null;
  el("focusDate").textContent = "-";
  el("focusHint").textContent = "Noch kein Trainingstag geladen";
  el("focusRecommendation").textContent = "-";
  el("focusRecommendationMeta").textContent = "Wird aus Readiness, Lastbalance und Baseline-Abweichung abgeleitet.";
  el("focusReadiness").textContent = "-";
  el("focusReadinessDelta").textContent = "-";
  el("focusRatio").textContent = "-";
  el("focusRatioMeta").textContent = "-";
  el("focusSync").textContent = "-";
  el("focusSyncMeta").textContent = "-";
  el("summaryAverageReadiness").textContent = "-";
  el("summaryAverageLoad").textContent = "-";
  el("relativeMetricGrid").innerHTML = "";
  el("readinessChart").innerHTML = "";
  el("loadChart").innerHTML = "";
  el("loadHeatmap").innerHTML = "";
  el("historyTable").innerHTML = "";
  el("activityHeadline").textContent = "Training des Fokus-Tags";
  el("activityList").innerHTML = "";
  el("unitIntro").textContent = "Die Vorschlaege folgen dem aktiven Modus.";
  el("unitCards").innerHTML = "";
  el("aiPrompt").value = "";
  document.querySelectorAll(".ribbon-card").forEach((node) => {
    node.dataset.tone = "neutral";
  });
}

function setLoggedOutState() {
  clearDashboard();
  el("garminStatus").textContent = "Bitte einloggen, um Garmin zu verbinden.";
}

function setNoDataState(account) {
  clearDashboard();
  el("garminStatus").textContent = account?.connected
    ? "Noch keine Trainingsdaten vorhanden. Fuehre Update oder Backfill aus."
    : "Garmin noch nicht verbunden.";
  el("focusSync").textContent = account?.connected ? safeText(account.sync_status, "connected") : "offline";
  el("focusSyncMeta").textContent = account?.sync_error || "Noch kein Sync verfuegbar.";
}

function getFilteredSeries() {
  const series = state.dashboard?.series || [];
  if (!series.length) return [];
  const latest = series[series.length - 1].date;
  return series.filter((item) => dateDistanceFromLatest(item.date, latest) < state.rangeDays);
}

function getActiveItem(series) {
  if (!series.length) return null;
  if (state.selectedDate) {
    const selected = series.find((item) => item.date === state.selectedDate);
    if (selected) return selected;
  }
  return series[series.length - 1];
}

function modeRecommendation(item) {
  if (!item) return "-";
  if (state.mode === "run") return item.recommendation_run;
  if (state.mode === "bike") return item.recommendation_bike;
  if (state.mode === "strength") return item.recommendation_strength;
  return item.recommendation_hybrid;
}

function modeUnits(item) {
  if (!item) return [];
  if (state.mode === "run") return item.units_run || [];
  if (state.mode === "bike") return item.units_bike || [];
  if (state.mode === "strength") return item.units_strength || [];
  return item.units_hybrid || [];
}

function renderOverview(filtered, active) {
  const account = state.dashboard?.account || {};
  const readinessValues = filtered.map((item) => item.readiness).filter((value) => Number.isFinite(value));
  const loadValues = filtered.map((item) => Number(item.load_day || 0));
  const avgReadiness = readinessValues.length
    ? readinessValues.reduce((sum, value) => sum + value, 0) / readinessValues.length
    : null;
  const avgLoad = loadValues.length
    ? loadValues.reduce((sum, value) => sum + value, 0) / loadValues.length
    : null;

  el("focusDate").textContent = safeText(active?.date);
  el("focusHint").textContent = active?.date === filtered[filtered.length - 1]?.date
    ? "Neuester verfuegbarer Tag im aktuellen Filter"
    : "Aus der Historie ausgewaehlter Tag";
  el("focusRecommendation").textContent = safeText(modeRecommendation(active));
  el("focusRecommendationMeta").textContent = active?.recommendation_day
    ? `Empfehlung gilt fuer ${active.recommendation_day}.`
    : "Noch keine Empfehlung berechnet.";

  el("focusReadiness").textContent = formatNumber(active?.readiness, 0);
  el("focusReadinessDelta").textContent = avgReadiness !== null && active?.readiness !== null && active?.readiness !== undefined
    ? `${formatSigned(Number(active.readiness) - avgReadiness, 1)} vs. Periodenschnitt`
    : safeText(active?.readiness_reason, "Keine Baseline verfuegbar");
  el("focusReadiness").closest(".ribbon-card").dataset.tone = scoreTone(active?.readiness);

  el("focusRatio").textContent = formatNumber(active?.ratio, 2);
  el("focusRatioMeta").textContent = safeText(active?.ratio_label, "Keine Ratio verfuegbar");
  el("focusRatio").closest(".ribbon-card").dataset.tone = ratioTone(active?.ratio);

  el("focusSync").textContent = safeText(account.sync_status, account.connected ? "connected" : "offline");
  el("focusSyncMeta").textContent = account.sync_error || (account.last_sync_at ? `Letzter Sync ${account.last_sync_at}` : "Noch kein Sync.");
  el("focusSync").closest(".ribbon-card").dataset.tone = syncTone(account.sync_status);

  el("summaryAverageReadiness").textContent = formatNumber(avgReadiness, 1);
  el("summaryAverageLoad").textContent = formatNumber(avgLoad, 1);
}

function renderRelativeMetrics(active) {
  const target = el("relativeMetricGrid");
  const metrics = active?.relative_metrics || {};
  const cards = Object.values(metrics).map((metric) => {
    const tone = metric?.state || "neutral";
    const baseline = metric.baseline === null || metric.baseline === undefined ? "-" : formatNumber(metric.baseline, 1);
    const deltaPct = metric.delta_pct === null || metric.delta_pct === undefined ? "-" : formatSigned(metric.delta_pct, 1, "%");
    return `
      <article class="relative-card" data-tone="${tone}">
        <div class="relative-head">
          <div>
            <div class="relative-title">${safeHtml(metric.label)}</div>
            <div class="muted-copy">${safeHtml(metric.band, "-")} | ${safeHtml(metric.n, "-")} Samples</div>
          </div>
          <div class="relative-value">${formatNumber(metric.current, 1)}</div>
        </div>
        <div class="relative-meta">
          <span>Baseline ${baseline}</span>
          <span>${deltaPct}</span>
        </div>
        <div class="progress">
          <div class="progress-fill" style="width:${metric.progress || 0}%"></div>
        </div>
      </article>
    `;
  });

  target.innerHTML = cards.join("") || '<div class="muted-copy">Keine baseline-relativen Morgenwerte vorhanden.</div>';
}

function chartPointY(value, minY, maxY, top, plotHeight) {
  const range = Math.max(1, maxY - minY);
  return top + ((maxY - value) / range) * plotHeight;
}

function drawLineChart(svgId, series, lines, activeDate) {
  const svg = el(svgId);
  if (!series.length) {
    svg.innerHTML = "";
    return;
  }

  const width = 920;
  const height = 320;
  const left = 54;
  const right = 26;
  const top = 26;
  const bottom = 44;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const values = [];

  lines.forEach((spec) => {
    series.forEach((item) => {
      if (Number.isFinite(item[spec.key])) values.push(Number(item[spec.key]));
    });
  });

  const minY = Math.min(...values, 0);
  const maxY = Math.max(...values, 1);
  const xStep = series.length > 1 ? plotWidth / (series.length - 1) : 0;

  let markup = "";
  for (let grid = 0; grid <= 4; grid += 1) {
    const y = top + (grid / 4) * plotHeight;
    const value = maxY - ((maxY - minY) * grid) / 4;
    markup += `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="rgba(173,212,202,0.08)" />`;
    markup += `<text x="${left - 12}" y="${y + 4}" text-anchor="end" font-size="11" fill="rgba(159,176,170,0.78)">${formatNumber(value, 0)}</text>`;
  }

  lines.forEach((spec) => {
    const points = series
      .map((item, index) => {
        const value = Number(item[spec.key]);
        if (!Number.isFinite(value)) return null;
        const x = left + index * xStep;
        const y = chartPointY(value, minY, maxY, top, plotHeight);
        return { x, y, value, date: item.date };
      })
      .filter(Boolean);

    if (!points.length) return;
    const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
    markup += `<path d="${path}" fill="none" stroke="${spec.color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />`;
    points.forEach((point) => {
      const isActive = point.date === activeDate;
      markup += `<circle cx="${point.x}" cy="${point.y}" r="${isActive ? 5.5 : 3.5}" fill="${isActive ? "#f2f4ee" : spec.color}" />`;
    });
  });

  series.forEach((item, index) => {
    const x = left + index * xStep;
    const fill = item.date === activeDate ? "#f2f4ee" : "rgba(159,176,170,0.8)";
    markup += `<text x="${x}" y="${height - 12}" text-anchor="middle" font-size="10" fill="${fill}">${item.date.slice(5)}</text>`;
  });

  svg.innerHTML = markup;
}

function renderHeatmap(filtered, activeDate) {
  const target = el("loadHeatmap");
  if (!filtered.length) {
    target.innerHTML = "";
    return;
  }

  const maxLoad = Math.max(...filtered.map((item) => Number(item.load_day || 0)), 1);
  target.innerHTML = filtered.map((item) => {
    const strength = Math.min(1, Number(item.load_day || 0) / maxLoad);
    const activeClass = item.date === activeDate ? "is-active" : "";
    return `<div class="heat-cell ${activeClass}" data-label="${item.date.slice(5)}" style="--strength:${strength.toFixed(3)}" title="${item.date}: ${formatNumber(item.load_day, 1)}"></div>`;
  }).join("");
}

function renderHistory(filtered, active) {
  const target = el("historyTable");
  target.innerHTML = filtered.slice().reverse().map((item) => {
    const activeClass = item.date === active?.date ? "is-active" : "";
    return `
      <tr class="history-row ${activeClass}" data-day="${item.date}">
        <td>${item.date}</td>
        <td>${formatNumber(item.readiness, 0)}</td>
        <td>${formatNumber(item.load_day, 1)}</td>
        <td>${formatNumber(item.ratio, 2)}</td>
        <td>${safeHtml(modeRecommendation(item))}</td>
      </tr>
    `;
  }).join("");

  target.querySelectorAll(".history-row").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedDate = row.dataset.day;
      renderDashboard();
    });
  });
}

function renderActivities(active) {
  el("activityHeadline").textContent = active?.date ? `Training am ${active.date}` : "Training des Fokus-Tags";
  const activities = active?.activities || [];
  if (!activities.length) {
    el("activityList").innerHTML = '<div class="muted-copy">Keine Einheiten fuer diesen Tag vorhanden.</div>';
    return;
  }

  el("activityList").innerHTML = activities.map((activity) => `
    <article class="activity-card">
      <div class="relative-head">
        <div>
          <div class="relative-title">${safeHtml(activity.name)}</div>
          <div class="muted-copy">${safeHtml(activity.type_key)} | ${safeHtml(activity.start_local)}</div>
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

function renderUnits(active) {
  const units = modeUnits(active);
  el("unitIntro").textContent = `Aktiver Modus: ${state.mode}.`;
  if (!units.length) {
    el("unitCards").innerHTML = '<div class="muted-copy">Keine konkreten Vorschlaege verfuegbar.</div>';
    return;
  }

  el("unitCards").innerHTML = units.map((unit, index) => `
    <article class="unit-card">
      <p class="eyebrow">Option ${index + 1}</p>
      <div>${safeHtml(unit)}</div>
    </article>
  `).join("");
}

async function updatePrompt() {
  const filtered = getFilteredSeries();
  const active = getActiveItem(filtered);
  if (!active) {
    el("aiPrompt").value = "";
    return;
  }

  try {
    const payload = await apiGet(`/api/ai-prompt?mode=${encodeURIComponent(state.mode)}&date=${encodeURIComponent(active.date)}`);
    el("aiPrompt").value = payload.prompt || "";
  } catch (error) {
    el("aiPrompt").value = `Fehler: ${error.message}`;
  }
}

function renderDashboard() {
  if (!state.dashboard || !state.dashboard.series || !state.dashboard.series.length) {
    setNoDataState(state.dashboard?.account);
    return;
  }

  const filtered = getFilteredSeries();
  if (!filtered.length) {
    setNoDataState(state.dashboard?.account);
    return;
  }

  const active = getActiveItem(filtered);
  if (!active) {
    setNoDataState(state.dashboard?.account);
    return;
  }

  state.selectedDate = active.date;
  renderOverview(filtered, active);
  renderRelativeMetrics(active);
  drawLineChart("readinessChart", filtered, [{ key: "readiness", color: "#63e6be" }], active.date);
  drawLineChart(
    "loadChart",
    filtered,
    [
      { key: "load_day", color: "#ffb85c" },
      { key: "load_7d", color: "#56d0b3" },
    ],
    active.date,
  );
  renderHeatmap(filtered, active.date);
  renderHistory(filtered, active);
  renderActivities(active);
  renderUnits(active);
  updatePrompt();
}

async function loadDashboard() {
  try {
    const payload = await apiGet("/api/dashboard");
    state.dashboard = payload;
    if (!payload?.series?.length) {
      setNoDataState(payload?.account);
      return;
    }
    renderDashboard();
    el("garminStatus").textContent = "Dashboard geladen.";
  } catch (error) {
    if (String(error.message || "").includes("einloggen")) {
      setLoggedOutState();
      return;
    }
    el("garminStatus").textContent = `Fehler: ${error.message}`;
  }
}

async function login() {
  const email = el("loginEmail").value;
  const password = el("loginPassword").value;
  const { error } = await requireSupabaseClient().auth.signInWithPassword({ email, password });
  if (error) {
    alert(error.message);
    return;
  }
  el("authStatus").textContent = "Anmeldung erfolgreich. Session wird geladen...";
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
  alert("Registrierung gestartet. Bestaetige deine E-Mail, falls Supabase dies verlangt.");
}

async function logout() {
  if (supabaseClient) {
    await supabaseClient.auth.signOut();
  }
  state.currentSession = null;
  setAuthUi(null);
  setLoggedOutState();
  el("authStatus").textContent = "Nicht eingeloggt";
}

async function connectGarmin() {
  try {
    const email = el("garminEmail").value.trim();
    const password = el("garminPassword").value.trim();
    if (!email || !password) {
      el("garminStatus").textContent = "Bitte Garmin E-Mail und Passwort eingeben.";
      return;
    }
    el("garminStatus").textContent = "Garmin Zugang wird geprueft...";
    await apiPost("/api/garmin/connect", { email, password });
    el("garminStatus").textContent = "Garmin Zugangsdaten gespeichert.";
    await loadDashboard();
  } catch (error) {
    el("garminStatus").textContent = `Fehler: ${error.message}`;
  }
}

async function updateData() {
  try {
    el("garminStatus").textContent = "Sync laeuft...";
    await apiPost("/api/update");
    await loadDashboard();
    el("garminStatus").textContent = "Update erfolgreich.";
  } catch (error) {
    el("garminStatus").textContent = `Fehler: ${error.message}`;
  }
}

async function backfillData() {
  try {
    el("garminStatus").textContent = "Backfill laeuft...";
    await apiPost("/api/backfill?days=28");
    await loadDashboard();
    el("garminStatus").textContent = "Backfill erfolgreich.";
  } catch (error) {
    el("garminStatus").textContent = `Fehler: ${error.message}`;
  }
}

function bindTabs() {
  el("tabBar").querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      el("tabBar").querySelectorAll(".tab-btn").forEach((node) => {
        node.classList.toggle("is-active", node === button);
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.panel === state.activeTab);
      });
    });
  });
}

function bindEvents() {
  hydrateRangeSelect();
  bindTabs();

  el("loginBtn").addEventListener("click", login);
  el("signupBtn").addEventListener("click", signup);
  el("logoutBtn").addEventListener("click", logout);
  el("connectGarminBtn").addEventListener("click", connectGarmin);
  el("updateBtn").addEventListener("click", updateData);
  el("backfillBtn").addEventListener("click", backfillData);

  el("rangeSelect").addEventListener("change", (event) => {
    state.rangeDays = Number(event.target.value);
    renderDashboard();
  });

  el("modeSelect").addEventListener("change", (event) => {
    state.mode = event.target.value;
    renderDashboard();
  });

  el("copyPromptBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el("aiPrompt").value);
      el("copyPromptBtn").textContent = "Kopiert";
      setTimeout(() => {
        el("copyPromptBtn").textContent = "Prompt kopieren";
      }, 1200);
    } catch (_error) {
      el("copyPromptBtn").textContent = "Fehler";
      setTimeout(() => {
        el("copyPromptBtn").textContent = "Prompt kopieren";
      }, 1200);
    }
  });
}

async function restoreSession() {
  if (!supabaseClient) {
    el("authStatus").textContent = missingConfigMessage();
    clearDashboard();
    el("garminStatus").textContent = missingConfigMessage();
    return;
  }

  const { data } = await supabaseClient.auth.getSession();
  state.currentSession = data?.session || null;
  const user = state.currentSession?.user || null;
  setAuthUi(user);
  el("authStatus").textContent = user ? `Eingeloggt als ${user.email}` : "Nicht eingeloggt";

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
    el("authStatus").textContent = user ? `Eingeloggt als ${user.email}` : "Nicht eingeloggt";
    window.setTimeout(async () => {
      if (state.currentSession?.access_token) {
        await loadDashboard();
      } else {
        setLoggedOutState();
      }
    }, 0);
  });
}

bindEvents();
setAuthUi(null);
restoreSession();
