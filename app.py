from flask import Flask, jsonify, render_template_string
import json
from pathlib import Path
from datetime import datetime, timedelta
from auth import requires_auth
from supabase import create_client
import os

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

app = Flask(__name__)

HISTORY_FILE = Path("training_history.json")


def load_history():
    if not HISTORY_FILE.exists():
        return {"days": {}}
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"days": {}}


def get_day_payload(history, day_str):
    return history.get("days", {}).get(day_str, {})


def get_day_load(history, day_str):
    summary = get_day_payload(history, day_str).get("summary", {})
    val = summary.get("training_load_sum")
    return float(val) if isinstance(val, (int, float)) else 0.0


def rolling_load(history, end_day_str, window_days):
    end_day = datetime.strptime(end_day_str, "%Y-%m-%d").date()
    total = 0.0
    for i in range(window_days):
        d = (end_day - timedelta(days=i)).isoformat()
        total += get_day_load(history, d)
    return round(total, 1)


def readiness_score(morning):
    if not morning:
        return None

    score = 50.0

    hrv = morning.get("hrv")
    if isinstance(hrv, (int, float)):
        score += (float(hrv) - 35.0) * 0.8

    resting_hr = morning.get("resting_hr")
    if isinstance(resting_hr, (int, float)):
        score -= (float(resting_hr) - 50.0) * 0.5

    sleep_h = morning.get("sleep_h")
    if isinstance(sleep_h, (int, float)):
        score += (float(sleep_h) - 7.0) * 2.0

    respiration = morning.get("respiration")
    if isinstance(respiration, (int, float)):
        score -= max(0.0, float(respiration) - 14.0) * 1.5

    score = int(max(1, min(99, round(score))))
    return score


def ratio_label(ratio):
    if ratio is None:
        return "keine Daten"
    if ratio < 0.8:
        return "unter Soll"
    if ratio <= 1.3:
        return "im Zielbereich"
    if ratio <= 1.5:
        return "erhöht"
    return "kritisch hoch"


def recommendation(score, ratio, mode="hybrid"):
    if score is None:
        return "Training nach Gefühl"
    if ratio is not None and ratio > 1.5:
        return "Belastung zu hoch – nur locker / Mobility"

    if mode == "run":
        if score < 40:
            return "Locker laufen"
        if score < 65:
            return "Moderater Lauf"
        if score < 80:
            return "Qualitätseinheit möglich"
        return "Harter Lauf möglich"

    if mode == "bike":
        if score < 40:
            return "Locker rollen"
        if score < 65:
            return "Moderate Radeinheit"
        if score < 80:
            return "Qualitätseinheit Rad möglich"
        return "Harter Radtag möglich"

    if mode == "strength":
        if score < 40:
            return "Nur Mobility"
        if score < 60:
            return "Moderates Krafttraining"
        if score < 80:
            return "Schweres Krafttraining möglich"
        return "Maximales Krafttraining möglich"

    if score < 40:
        return "Erholung oder Mobility"
    if score < 60:
        return "Moderater Trainingstag"
    if score < 80:
        return "Qualität möglich"
    return "Harter Qualitätstag möglich"


def suggested_units(score, ratio, mode="hybrid"):
    if score is None:
        return [
            "Datenlage zu dünn: 30-45 min locker nach Gefühl",
            "Optional 10-15 min Mobility",
        ]

    if ratio is not None and ratio > 1.5:
        return [
            "30-45 min sehr locker in Z1",
            "oder 20-30 min Mobility / Spazieren",
            "keine harte Qualität, kein schweres Krafttraining",
        ]

    if mode == "run":
        if score < 40:
            return [
                "30-40 min locker laufen oder gehen",
                "optional 6 x 20 s lockere Steigerungen nur wenn Beine gut",
            ]
        if score < 65:
            return [
                "45-60 min lockerer bis moderater Dauerlauf",
                "alternativ 30-45 min locker + 6 x 20 s Steigerungen",
            ]
        if score < 80:
            return [
                "Qualität Lauf: 6 x 3 min zügig mit 2 min locker",
                "alternativ 4 x 5 min an Schwelle mit 2-3 min locker",
            ]
        return [
            "Harter Lauf: 5 x 4 min hart mit 3 min locker",
            "alternativ 8 x 400 m zügig mit lockerer Trabpause",
        ]

    if mode == "bike":
        if score < 40:
            return [
                "45-60 min sehr locker rollen in Z1/Z2",
                "hohe Kadenz, keine Intervalle",
            ]
        if score < 65:
            return [
                "60-90 min locker bis moderat in Z2",
                "alternativ 3 x 8 min Sweet Spot kontrolliert",
            ]
        if score < 80:
            return [
                "Qualität Rad: 4 x 8 min zügig mit 4 min locker",
                "alternativ 5 x 5 min hart mit 3 min locker",
            ]
        return [
            "Harter Radtag: 6 x 4 min VO2 mit 4 min locker",
            "alternativ 3 x 12 min Schwelle mit 6 min locker",
        ]

    if mode == "strength":
        if score < 40:
            return [
                "Nur Mobility, Technik oder sehr leichte Maschinenrunde",
                "kein schweres Beintraining",
            ]
        if score < 60:
            return [
                "Moderates Krafttraining Ganzkörper, 2-3 Sätze",
                "1-3 Wiederholungen im Tank lassen",
            ]
        if score < 80:
            return [
                "Schweres Krafttraining möglich, Hauptlifts fokussieren",
                "z. B. 3-5 Sätze Grundübungen, moderates Volumen",
            ]
        return [
            "Schwerer Krafttag gut vertretbar",
            "z. B. Hauptübungen schwer + 1-2 Zusatzübungen",
        ]

    # hybrid = run + bike + strength
    if score < 40:
        return [
            "Option 1: 30-40 min locker Run oder Bike",
            "Option 2: 20-30 min Mobility / Stretching",
            "Option 3: nur leichtes Krafttraining ohne schwere Sätze",
        ]
    if score < 60:
        return [
            "Run: 45-60 min locker bis moderat",
            "Bike: 60-90 min locker Z2",
            "Strength: normale eGym-Runde / moderates Ganzkörpertraining",
        ]
    if score < 80:
        return [
            "Run: 6 x 3 min zügig oder 4 x 5 min Schwelle",
            "Bike: 4 x 8 min zügig oder 5 x 5 min hart",
            "Strength: schweres Krafttraining möglich, aber nicht maximal",
        ]
    return [
        "Run: harter Qualitätstag möglich",
        "Bike: harter Intervalltag möglich",
        "Strength: schwerer Krafttag gut vertretbar",
    ]


def build_series(history):
    days = sorted(history.get("days", {}).keys())
    series = []

    for day in days:
        payload = history["days"].get(day, {})
        morning = payload.get("morning") or {}
        summary = payload.get("summary") or {}

        load7 = rolling_load(history, day, 7)
        load28 = rolling_load(history, day, 28)
        ratio = round((load7 / 7.0) / (load28 / 28.0), 2) if load28 > 0 else None
        readiness = readiness_score(morning)

        series.append({
            "date": day,
            "readiness": readiness,
            "load_day": summary.get("training_load_sum") or 0,
            "load_7d": load7,
            "load_28d": load28,
            "ratio": ratio,
            "ratio_label": ratio_label(ratio),
            "resting_hr": morning.get("resting_hr"),
            "hrv": morning.get("hrv"),
            "respiration": morning.get("respiration"),
            "sleep_h": morning.get("sleep_h"),
            "spo2": morning.get("pulse_ox"),
            "recommendation_hybrid": recommendation(readiness, ratio, "hybrid"),
            "recommendation_run": recommendation(readiness, ratio, "run"),
            "recommendation_bike": recommendation(readiness, ratio, "bike"),
            "recommendation_strength": recommendation(readiness, ratio, "strength"),
            "units_hybrid": suggested_units(readiness, ratio, "hybrid"),
            "units_run": suggested_units(readiness, ratio, "run"),
            "units_bike": suggested_units(readiness, ratio, "bike"),
            "units_strength": suggested_units(readiness, ratio, "strength"),
        })

    return series


def format_num(v):
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v) if v is not None else "-"


def build_ai_prompt(latest, mode="hybrid"):
    if not latest:
        return "Keine Daten verfügbar."

    if mode == "run":
        target = "Lauftraining"
        mode_rec = latest.get("recommendation_run")
    elif mode == "bike":
        target = "Radtraining"
        mode_rec = latest.get("recommendation_bike")
    elif mode == "strength":
        target = "Krafttraining"
        mode_rec = latest.get("recommendation_strength")
    else:
        target = "Hybridtraining aus Run, Bike und Strength"
        mode_rec = latest.get("recommendation_hybrid")

    prompt = f"""Du bist mein nüchterner Trainingsberater. Beurteile nur anhand der folgenden Garmin-Daten, ob morgen eher Erholung, moderates Training oder ein Qualitätstag sinnvoll ist.

Regeln:
- Antworte knapp und konkret.
- Keine Motivation, kein Coaching-Ton, keine medizinischen Aussagen.
- Bevorzuge konservative Entscheidungen, wenn Last oder Tagesform grenzwertig sind.
- Gib am Ende genau diese Punkte aus:
  1. Gesamturteil
  2. Empfohlene Einheit morgen
  3. Was ich vermeiden sollte
  4. Begründung in 3 kurzen Punkten

Daten:
Datum: {latest.get("date")}
Modus: {mode}
Zielbereich: {target}

Readiness: {format_num(latest.get("readiness"))}/99
Ruhepuls: {format_num(latest.get("resting_hr"))}
HRV: {format_num(latest.get("hrv"))}
Atmung: {format_num(latest.get("respiration"))}
SpO2: {format_num(latest.get("spo2"))}
Schlaf: {format_num(latest.get("sleep_h"))} h

Tages-Load heute: {format_num(latest.get("load_day"))}
7d Load: {format_num(latest.get("load_7d"))}
28d Load: {format_num(latest.get("load_28d"))}
7d/28d Ratio: {format_num(latest.get("ratio"))} ({latest.get("ratio_label")})

Interne Basisausgabe meines Dashboards:
- Hybrid: {latest.get("recommendation_hybrid")}
- Run: {latest.get("recommendation_run")}
- Bike: {latest.get("recommendation_bike")}
- Strength: {latest.get("recommendation_strength")}

Bitte gib eine konkrete Empfehlung für morgen für {target}. Falls die Daten eher gegen maximale Intensität sprechen, sage das klar."""
    return prompt


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
</head>
<body>
<button onclick="updateData()">Daten aktualisieren</button>

<script>
async function updateData(){
  await fetch("/api/update")
  location.reload()
}
</script>
  <div class="wrap">
    <h1>Garmin Training Dashboard</h1>
    <div class="sub">Readiness, 7d/28d Load, konkrete Einheiten und KI-Prompt aus deiner training_history.json</div>

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

function updatePrompt() {
  if (!dashboardData || !dashboardData.latest) return;
  const mode = el("modeSelect").value;
  fetch(`/api/ai-prompt?mode=${encodeURIComponent(mode)}`)
    .then(r => r.json())
    .then(data => {
      el("aiPrompt").value = data.prompt || "";
      el("todayRec").textContent = modeRecommendation(dashboardData.latest, mode) || "-";
    });
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

fetch("/api/dashboard")
  .then(r => r.json())
  .then(render);
</script>
</body>
</html>
"""


@app.route("/api/history")
@requires_auth
def get_history():

    res = supabase.table("training_days") \
        .select("*") \
        .order("date", desc=True) \
        .limit(30) \
        .execute()

    return res.data


@app.route("/api/dashboard")
def api_dashboard():
    history = load_history()
    series = build_series(history)
    latest = series[-1] if series else None
    return jsonify({"latest": latest, "series": series})


@app.route("/api/ai-prompt")
def api_ai_prompt():
    from flask import request
    mode = request.args.get("mode", "hybrid")
    if mode not in {"hybrid", "run", "bike", "strength"}:
        mode = "hybrid"

    history = load_history()
    series = build_series(history)
    latest = series[-1] if series else None
    return jsonify({"mode": mode, "prompt": build_ai_prompt(latest, mode)})


@app.route("/")
@requires_auth
def index():
    return render_template_string(HTML)

import subprocess

@app.route("/api/update")
@requires_auth
def update_data():
    from garmin_hybrid_report_v61_full import main_logic

    data = main_logic(mode="hybrid")

    supabase.table("training_days").upsert({
        "date": data["date"],
        "data": data
    }).execute()

    return {"status": "updated", "date": data["date"]}

if __name__ == "__main__":
    app.run(debug=True)
