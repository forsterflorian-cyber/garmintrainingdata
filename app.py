from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from crypto_utils import encrypt, decrypt
from auth_supabase import require_user

from flask import Flask, jsonify, render_template_string, request
from supabase import create_client


from garmin_hybrid_report_v62_supabase_ready import (
    ActivitySummary,
    build_ai_prompt as report_build_ai_prompt,
    load_client,
    main_logic_for_day,
    get_recent_activities,
)

from supabase import create_client
import os

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

app = Flask(__name__)


HTML = """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Garmin Training Dashboard</title>
  <style>
    :root {
      --bg: #0b1020;
      --panel: #151b2f;
      --panel-2: #1b2340;
      --text: #ecf1ff;
      --muted: #a8b3d1;
      --ok: #35c759;
      --warn: #ffcc00;
      --bad: #ff453a;
      --border: #2b3459;
      --accent: #7aa2ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background: linear-gradient(180deg, #0b1020 0%, #10172d 100%);
      color: var(--text);
    }
    .wrap { max-width: 1600px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px 0; font-size: 32px; }
    .sub { color: var(--muted); margin-bottom: 24px; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
    .card {
      background: rgba(21,27,47,0.9);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.18);
    }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }
    .kpi-label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
    .kpi-value { font-size: 34px; font-weight: 700; letter-spacing: -0.02em; }
    .kpi-small { color: var(--muted); margin-top: 6px; font-size: 14px; }
    .section-title { font-size: 18px; font-weight: 700; margin-bottom: 12px; }
    .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .metric-box {
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 12px;
    }
    .metric-box .label { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .metric-box .value { font-size: 24px; font-weight: 700; }
    .flags { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .flag { padding: 14px; border-radius: 16px; text-align: center; border: 1px solid var(--border); background: var(--panel-2); }
    .flag .title { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
    .flag .value { font-size: 20px; font-weight: 800; }
    .chart {
      width: 100%;
      height: 280px;
      background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.00));
      border-radius: 18px;
      border: 1px solid var(--border);
      padding: 8px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; }
    th { color: var(--muted); font-weight: 600; }
    .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
    select, button {
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
      font: inherit;
    }
    button { cursor: pointer; }
    button:hover { border-color: var(--accent); }
    textarea {
      width: 100%;
      min-height: 280px;
      background: #0d1326;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px;
      font: 13px/1.45 Consolas, monospace;
      resize: vertical;
    }
    .hint { color: var(--muted); font-size: 13px; margin-top: 8px; }
    @media (max-width: 900px) {
      .span-3, .span-4, .span-6, .span-8, .span-12 { grid-column: span 12; }
      .metrics, .flags { grid-template-columns: repeat(2, 1fr); }
      #unitsList { grid-template-columns: 1fr !important; }
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
</head>
<body>
<button onclick="updateData()">Daten aktualisieren</button>
<div id="authBox" style="max-width:420px;margin:24px auto;padding:20px;background:#151b2f;border:1px solid #2b3459;border-radius:16px;">
  <h2 style="margin-top:0;">Login</h2>
  <input id="loginEmail" type="email" placeholder="E-Mail" style="width:100%;margin-bottom:10px;padding:10px;border-radius:10px;border:1px solid #2b3459;background:#0d1326;color:#ecf1ff;">
  <input id="loginPassword" type="password" placeholder="Passwort" style="width:100%;margin-bottom:10px;padding:10px;border-radius:10px;border:1px solid #2b3459;background:#0d1326;color:#ecf1ff;">
  <div style="display:flex;gap:10px;">
    <button onclick="login()">Login</button>
    <button onclick="signup()">Registrieren</button>
    <button onclick="logout()">Logout</button>
  </div>
  <div id="authStatus" style="margin-top:10px;color:#a8b3d1;">Nicht eingeloggt</div>
</div>
<script>
const SUPABASE_URL = "SUPABASE_URL";
const SUPABASE_ANON_KEY = "SUPABASE_KEY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

async function getToken() {
  const { data } = await supabaseClient.auth.getSession();
  return data.session?.access_token || null;
}

async function apiGet(url) {
  const token = await getToken();

  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(json.error || `HTTP ${res.status}`);
  }

  return json;
}

async function apiPost(url, body = null) {
  const token = await getToken();

  const res = await fetch(url, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": "application/json"
    },
    body: body ? JSON.stringify(body) : null
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(json.error || `HTTP ${res.status}`);
  }

  return json;
}

async function refreshAuthStatus() {
  const { data } = await supabaseClient.auth.getSession();
  const user = data.session?.user;

  document.getElementById("authStatus").textContent = user
    ? `Eingeloggt als ${user.email}`
    : "Nicht eingeloggt";
}

async function login() {
  const email = document.getElementById("loginEmail").value;
  const password = document.getElementById("loginPassword").value;

  const { error } = await supabaseClient.auth.signInWithPassword({ email, password });

  if (error) {
    alert(error.message);
    return;
  }

  await refreshAuthStatus();
  await loadDashboard();
}

async function loadDashboard() {
  try {
    const data = await apiGet("/api/dashboard");
    render(data);
  } catch (e) {
    console.error(e);
    document.getElementById("authStatus").textContent = `Fehler: ${e.message}`;
  }
}

async function signup() {
  const email = document.getElementById("loginEmail").value;
  const password = document.getElementById("loginPassword").value;

  const { error } = await supabaseClient.auth.signUp({ email, password });

  if (error) {
    alert(error.message);
    return;
  }

  alert("Registrierung gestartet. Je nach Supabase-Einstellung musst du evtl. deine E-Mail bestätigen.");
  await refreshAuthStatus();
}

async function logout() {
  await supabaseClient.auth.signOut();
  await refreshAuthStatus();
  location.reload();
}

async function updateData() {
  try {
    await apiPost("/api/update");
    await loadDashboard();
  } catch (e) {
    alert(e.message);
  }
}

</script>
  <div class="wrap">
    <h1>Garmin Training Dashboard</h1>
<div class="sub">Readiness, 7d/28d Load, konkrete Einheiten und KI-Prompt aus Supabase</div>

    <div class="grid">
      <div class="card span-3">
        <div class="kpi-label">Heute</div>
        <div class="kpi-value" id="todayDate">-</div>
        <div class="kpi-small">letzter verfügbarer Tag</div>
      </div>

      <div class="card span-3">
        <div class="kpi-label">Readiness</div>
        <div class="kpi-value" id="todayReadiness">-</div>
        <div class="kpi-small">vereinfachter Score 1–99</div>
      </div>

      <div class="card span-3">
        <div class="kpi-label">7d / 28d Ratio</div>
        <div class="kpi-value" id="todayRatio">-</div>
        <div class="kpi-small" id="todayRatioLabel">-</div>
      </div>

      <div class="card span-3">
        <div class="kpi-label">Empfehlung</div>
        <div class="kpi-value" style="font-size:22px;line-height:1.2" id="todayRec">-</div>
        <div class="kpi-small">je nach ausgewähltem Modus</div>
      </div>

      <div class="card span-8">
        <div class="section-title">Readiness Verlauf</div>
        <svg id="readinessChart" class="chart" viewBox="0 0 800 280" preserveAspectRatio="none"></svg>
      </div>

      <div class="card span-4">
        <div class="section-title">Morgenwerte heute</div>
        <div class="metrics">
          <div class="metric-box">
            <div class="label">Ruhepuls</div>
            <div class="value" id="mRestingHr">-</div>
          </div>
          <div class="metric-box">
            <div class="label">HRV</div>
            <div class="value" id="mHrv">-</div>
          </div>
          <div class="metric-box">
            <div class="label">Atmung</div>
            <div class="value" id="mResp">-</div>
          </div>
          <div class="metric-box">
            <div class="label">Schlaf</div>
            <div class="value" id="mSleep">-</div>
          </div>
        </div>
      </div>

      <div class="card span-8">
        <div class="section-title">Load Verlauf</div>
        <svg id="loadChart" class="chart" viewBox="0 0 800 280" preserveAspectRatio="none"></svg>
      </div>

      <div class="card span-4">
        <div class="section-title">Trainings-Ampel</div>
        <div class="flags">
          <div class="flag">
            <div class="title">Locker</div>
            <div class="value" id="flagEasy">-</div>
          </div>
          <div class="flag">
            <div class="title">Qualität</div>
            <div class="value" id="flagQuality">-</div>
          </div>
          <div class="flag">
            <div class="title">Schwer Kraft</div>
            <div class="value" id="flagStrength">-</div>
          </div>
          <div class="flag">
            <div class="title">Max Test</div>
            <div class="value" id="flagMax">-</div>
          </div>
        </div>
      </div>
<div class="card span-12">
  <div class="section-title">Heutige Einheiten</div>
  <table>
    <thead>
      <tr>
        <th>Start</th>
        <th>Typ</th>
        <th>Name</th>
        <th>Dauer</th>
        <th>ØHF</th>
        <th>MaxHF</th>
        <th>TEa</th>
        <th>TEan</th>
        <th>Load</th>
      </tr>
    </thead>
    <tbody id="todayActivitiesTable"></tbody>
  </table>
</div>
      <div class="card span-12">
        <div class="section-title">Empfohlene Einheiten</div>
        <div class="hint" id="unitsIntro">Konkrete Optionen passend zum gewählten Modus.</div>
        <div id="unitsList" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px;"></div>
      </div>

      <div class="card span-12">
        <div class="section-title">KI-Prompt</div>
        <div class="toolbar">
          <label for="modeSelect">Modus</label>
          <select id="modeSelect">
            <option value="hybrid">hybrid</option>
            <option value="run">run</option>
            <option value="bike">bike</option>
            <option value="strength">strength</option>
          </select>
          <button id="copyPromptBtn">Prompt kopieren</button>
        </div>
        <textarea id="aiPrompt" spellcheck="false"></textarea>
        <div class="hint">Der Prompt nutzt nur die wichtigsten Entscheidungsdaten und ist für eine knappe KI-Empfehlung formuliert.</div>
      </div>

      <div class="card span-12">
        <div class="section-title">Letzte Tage</div>
        <table>
          <thead>
            <tr>
              <th>Datum</th>
              <th>Readiness</th>
              <th>Tages-Load</th>
              <th>7d Load</th>
              <th>28d Load</th>
              <th>Ratio</th>
              <th>Empfehlung</th>
            </tr>
          </thead>
          <tbody id="historyTable"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>
function el(id) { return document.getElementById(id); }

let dashboardData = null;

function scoreColor(v) {
  if (v == null) return "#a8b3d1";
  if (v < 40) return "#ff453a";
  if (v < 60) return "#ffcc00";
  return "#35c759";
}

function ratioColor(v) {
  if (v == null) return "#a8b3d1";
  if (v > 1.5) return "#ff453a";
  if (v > 1.3 || v < 0.8) return "#ffcc00";
  return "#35c759";
}

function buildFlags(item) {
  const score = item.readiness;
  const ratio = item.ratio;
  let flags = { easy: "JA", quality: "NEIN", strength: "NEIN", max: "NEIN" };
  if (score == null) return flags;
  if (ratio != null && ratio > 1.5) return flags;
  if (score >= 60) flags.quality = "JA";
  if (score >= 60) flags.strength = "JA";
  if (score >= 82) flags.max = "JA";
  return flags;
}

function polylinePath(data, valueKey, minY, maxY, width, height, padding) {
  const valid = data.filter(d => d[valueKey] != null);
  if (!valid.length) return "";
  const xStep = data.length > 1 ? (width - padding * 2) / (data.length - 1) : 0;
  return data.map((d, i) => {
    const v = d[valueKey];
    if (v == null) return null;
    const x = padding + i * xStep;
    const y = padding + (maxY - v) / (maxY - minY) * (height - padding * 2);
    return `${x},${y}`;
  }).filter(Boolean).join(" ");
}

function drawChart(svgId, data, lines) {
  const svg = el(svgId);
  const width = 800, height = 280, padding = 24;

  let values = [];
  lines.forEach(line => {
    data.forEach(d => {
      const v = d[line.key];
      if (v != null) values.push(v);
    });
  });

  if (!values.length) {
    svg.innerHTML = "";
    return;
  }

  const minY = Math.min(...values) * 0.9;
  const maxY = Math.max(...values) * 1.1;

  let html = "";
  for (let i = 0; i < 4; i++) {
    const y = padding + ((height - padding * 2) / 3) * i;
    html += `<line x1="${padding}" y1="${y}" x2="${width-padding}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-width="1" />`;
  }

  lines.forEach(line => {
    const pts = polylinePath(data, line.key, minY, maxY, width, height, padding);
    if (pts) html += `<polyline fill="none" stroke="${line.color}" stroke-width="3" points="${pts}" />`;
  });

  data.forEach((d, i) => {
    const xStep = data.length > 1 ? (width - padding * 2) / (data.length - 1) : 0;
    const x = padding + i * xStep;
    html += `<text x="${x}" y="${height-8}" font-size="10" text-anchor="middle" fill="#a8b3d1">${d.date.slice(5)}</text>`;
  });

  svg.innerHTML = html;
}

function modeRecommendation(item, mode) {
  if (mode === "run") return item.recommendation_run;
  if (mode === "bike") return item.recommendation_bike;
  if (mode === "strength") return item.recommendation_strength;
  return item.recommendation_hybrid;
}

function modeUnits(item, mode) {
  if (mode === "run") return item.units_run || [];
  if (mode === "bike") return item.units_bike || [];
  if (mode === "strength") return item.units_strength || [];
  return item.units_hybrid || [];
}

async function updatePrompt() {
  if (!dashboardData || !dashboardData.latest) return;
  const mode = el("modeSelect").value;

  try {
    const data = await apiGet(`/api/ai-prompt?mode=${encodeURIComponent(mode)}`);
    el("aiPrompt").value = data.prompt || "";
    el("todayRec").textContent = modeRecommendation(dashboardData.latest, mode) || "-";
  } catch (e) {
    el("aiPrompt").value = `Fehler: ${e.message}`;
  }
}

function render(data) {
  dashboardData = data;
  const latest = data.latest;
  if (!latest) return;

  el("todayDate").textContent = latest.date;
  el("todayReadiness").textContent = latest.readiness ?? "-";
  el("todayReadiness").style.color = scoreColor(latest.readiness);

  el("todayRatio").textContent = latest.ratio ?? "-";
  el("todayRatio").style.color = ratioColor(latest.ratio);
  el("todayRatioLabel").textContent = latest.ratio_label ?? "-";

  el("mRestingHr").textContent = latest.resting_hr ?? "-";
  el("mHrv").textContent = latest.hrv ?? "-";
  el("mResp").textContent = latest.respiration ?? "-";
  el("mSleep").textContent = latest.sleep_h ?? "-";

  const flags = buildFlags(latest);
  el("flagEasy").textContent = flags.easy;
  el("flagQuality").textContent = flags.quality;
  el("flagStrength").textContent = flags.strength;
  el("flagMax").textContent = flags.max;

const acts = latest.activities || [];

el("todayActivitiesTable").innerHTML = acts.length
  ? acts.map(a => `
    <tr>
      <td>${a.start_local || "-"}</td>
      <td>${a.type_key || "-"}</td>
      <td>${a.name || "-"}</td>
      <td>${a.duration_min ?? "-"}</td>
      <td>${a.avg_hr ?? "-"}</td>
      <td>${a.max_hr ?? "-"}</td>
      <td>${a.aerobic_te ?? "-"}</td>
      <td>${a.anaerobic_te ?? "-"}</td>
      <td>${a.training_load ?? "-"}</td>
    </tr>
  `).join("")
  : `<tr><td colspan="9">Keine Einheiten für diesen Tag vorhanden.</td></tr>`;
  
  drawChart("readinessChart", data.series.slice(-21), [
    { key: "readiness", color: "#35c759" }
  ]);

  drawChart("loadChart", data.series.slice(-21), [
    { key: "load_day", color: "#7aa2ff" },
    { key: "load_7d", color: "#ffcc00" }
  ]);

  const mode = el("modeSelect").value;
  el("todayRec").textContent = modeRecommendation(latest, mode) || "-";

  const units = modeUnits(latest, mode);
  const modeLabel = mode === "hybrid" ? "hybrid = run + bike + strength" : mode;
  el("unitsIntro").textContent = `Konkrete Optionen passend zum gewählten Modus (${modeLabel}).`;
  el("unitsList").innerHTML = units.map((u, idx) => `
    <div style="background:var(--panel-2);border:1px solid var(--border);border-radius:16px;padding:14px;">
      <div style="color:var(--muted);font-size:12px;margin-bottom:8px;">Option ${idx + 1}</div>
      <div style="font-weight:700;line-height:1.4;">${u}</div>
    </div>
  `).join("");

  const rows = data.series.slice().reverse().slice(0, 14).map(d => `
    <tr>
      <td>${d.date}</td>
      <td style="color:${scoreColor(d.readiness)};font-weight:700">${d.readiness ?? "-"}</td>
      <td>${d.load_day}</td>
      <td>${d.load_7d}</td>
      <td>${d.load_28d}</td>
      <td style="color:${ratioColor(d.ratio)};font-weight:700">${d.ratio ?? "-"}</td>
      <td>${modeRecommendation(d, mode)}</td>
    </tr>
  `).join("");

  el("historyTable").innerHTML = rows;
  updatePrompt();
}

el("modeSelect").addEventListener("change", () => {
  if (dashboardData) render(dashboardData);
});

el("copyPromptBtn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el("aiPrompt").value);
    el("copyPromptBtn").textContent = "Kopiert";
    setTimeout(() => el("copyPromptBtn").textContent = "Prompt kopieren", 1200);
  } catch (e) {
    el("copyPromptBtn").textContent = "Fehler";
    setTimeout(() => el("copyPromptBtn").textContent = "Prompt kopieren", 1200);
  }
});

(async () => {
  await refreshAuthStatus();
  await loadDashboard();
})();
</script>
</body>
</html>
"""


def _mode_or_default(value: Optional[str]) -> str:
    return value if value in {"hybrid", "run", "bike", "strength"} else "hybrid"


def _fetch_rows(user_id: str, limit: int = 120) -> List[Dict[str, Any]]:
    res = (
        supabase.table("training_days")
        .select("user_id,date,data")
        .eq("user_id", user_id)
        .order("date", desc=False)
        .limit(limit)
        .execute()
    )
    return res.data or []


def _history_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    history: Dict[str, Any] = {"days": {}}
    for row in rows:
        payload = row.get("data") or {}
        day = payload.get("date") or row.get("date")
        if not day:
            continue
        history["days"][day] = {
            "morning": payload.get("morning"),
            "summary": payload.get("summary") or {},
        }
    return history


def _payload_to_series_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    morning = payload.get("morning") or {}
    load_metrics = payload.get("load_metrics") or {}
    recs = payload.get("recommendations") or {}
    units = payload.get("units") or {}
    summary = payload.get("summary") or {}
    readiness = payload.get("readiness") or {}

    return {
        "date": payload.get("date"),
        "readiness": readiness.get("score"),
        "load_day": summary.get("training_load_sum", 0),
        "load_7d": load_metrics.get("load_7d"),
        "load_28d": load_metrics.get("load_28d"),
        "ratio": load_metrics.get("load_ratio"),
        "ratio_label": load_metrics.get("load_ratio_label"),
        "resting_hr": morning.get("resting_hr"),
        "hrv": morning.get("hrv"),
        "respiration": morning.get("respiration"),
        "sleep_h": morning.get("sleep_h"),
        "spo2": morning.get("pulse_ox"),
        "recommendation_hybrid": recs.get("hybrid"),
        "recommendation_run": recs.get("run"),
        "recommendation_bike": recs.get("bike"),
        "recommendation_strength": recs.get("strength"),
        "units_hybrid": units.get("hybrid", []),
        "units_run": units.get("run", []),
        "units_bike": units.get("bike", []),
        "units_strength": units.get("strength", []),
        "activities": payload.get("activities", []),
        "recommendation_day": payload.get("recommendation_day"),
        "ai_prompt": payload.get("ai_prompt"),
    }


def _build_series(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.get("data") or {}
        if payload.get("date"):
            items.append(_payload_to_series_item(payload))
    items.sort(key=lambda item: item["date"])
    return items


def _build_prompt_from_payload(payload: Optional[Dict[str, Any]], mode: str) -> str:
    if not payload:
        return "Keine Daten verfügbar."

    mode = _mode_or_default(mode)
    recommendation_day = payload.get("recommendation_day") or payload.get("date")
    morning = payload.get("morning")
    summary = payload.get("summary") or {}
    load_metrics = payload.get("load_metrics") or {}
    activities = [ActivitySummary(**a) for a in (payload.get("activities") or [])]
    recommendations = payload.get("recommendations") or {}
    units = (payload.get("units") or {}).get(mode) or (payload.get("units") or {}).get("hybrid", [])

    return report_build_ai_prompt(
        mode=mode,
        recommendation_day=recommendation_day,
        today_day=payload.get("date"),
        latest_morning=None if not morning else type("MorningProxy", (), morning)(),
        today_summary=summary,
        today_load_metrics=load_metrics,
        today_activities=activities,
        dashboard_recommendations=recommendations,
        units=units,
    )


def _upsert_payload(user_id: str, payload: Dict[str, Any]) -> None:
    (
        supabase.table("training_days")
        .upsert(
            {
                "user_id": user_id,
                "date": payload["date"],
                "data": payload,
            },
            on_conflict="user_id,date",
        )
        .execute()
    )


@app.route("/api/history")
@require_user
def api_history():
    rows = list(reversed(_fetch_rows(request.user_id, limit=30)))
    return {"rows": rows}


@app.get("/api/dashboard")
@require_user
def dashboard():
    rows = _fetch_rows(request.user_id, limit=365)
    series = _build_series(rows)
    latest = series[-1] if series else None

    return {
        "latest": latest,
        "series": series,
    }


@app.route("/api/ai-prompt")
@require_user
def api_ai_prompt():
    mode = _mode_or_default(request.args.get("mode", "hybrid"))
    rows = _fetch_rows(request.user_id, limit=1)
    latest_payload = rows[-1].get("data") if rows else None
    return jsonify({
        "mode": mode,
        "prompt": _build_prompt_from_payload(latest_payload, mode)
    })


@app.route("/")
def index():
    return render_template_string(HTML)


@app.post("/api/update")
@require_user
def update():
    creds = get_garmin_credentials(request.user_id)

    if not creds:
        return {"error": "garmin not connected"}, 400

    email, password = creds

    client = client = load_client(email=email,password=password,user_id=request.user_id,
)

    rows = _fetch_rows(request.user_id, limit=365)
    history = _history_from_rows(rows)
    recent_activities = get_recent_activities(client, 400)

    today = date.today().isoformat()

    payload = main_logic_for_day(
        day=today,
        mode="hybrid",
        history=history,
        client=client,
        recent_activities=recent_activities,
        persist_history=False,
    )

    _upsert_payload(request.user_id, payload)

    return {"status": "ok", "date": payload["date"]}


@app.route("/api/backfill", methods=["POST"])
@require_user
def backfill_data():
    days = int(request.args.get("days", "28"))
    days = max(1, min(days, 180))

    creds = get_garmin_credentials(request.user_id)
    if not creds:
        return {"error": "garmin not connected"}, 400

    email, password = creds
    client = load_client(email=email, password=password,user_id=request.user_id,)

    rows = _fetch_rows(request.user_id, limit=365)
    history = _history_from_rows(rows)
    recent_activities = get_recent_activities(client, 400)

    results: List[str] = []

    for offset in range(days - 1, -1, -1):
        day = (date.today() - timedelta(days=offset)).isoformat()

        payload = main_logic_for_day(
            day=day,
            mode="hybrid",
            history=history,
            client=client,
            recent_activities=recent_activities,
            persist_history=False,
        )

        _upsert_payload(request.user_id, payload)

        history["days"][day] = {
            "morning": payload.get("morning"),
            "summary": payload.get("summary") or {},
        }

        results.append(day)

    return {
        "status": "backfilled",
        "days": len(results),
        "dates": results,
    }

@app.post("/api/garmin/connect")
@require_user
def connect_garmin():

    data = request.json

    email = data["email"]
    password = data["password"]

    email_enc = encrypt(email)
    pw_enc = encrypt(password)

    supabase.table("user_garmin_accounts").upsert({
        "user_id": request.user_id,
        "garmin_email_enc": email_enc,
        "garmin_password_enc": pw_enc
    }).execute()

    return {"status": "ok"}
    
def get_garmin_credentials(user_id):

    res = supabase.table("user_garmin_accounts") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not res.data:
        return None

    row = res.data[0]

    email = decrypt(row["garmin_email_enc"])
    password = decrypt(row["garmin_password_enc"])

    return email, password
    
if __name__ == "__main__":
    app.run(debug=True)
