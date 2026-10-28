/* Added: the model cards on the overview, the heart risk predictor and the hospitals list in the ward panel.
   Uses the helpers in app.js (S, fmt, esc, showPage, openWard, ...). Model results come from the FastAPI backend
   (/api) when it is running. On a static host such as GitHub Pages there is no backend, so the same data is read
   from static-api/ (written by src/static_api.py) and the three models run in the browser via model-runtime.js.
   The hospital list is read from the pipeline's files directly. Charts are in the Power BI report. */
"use strict";

const API = "/api";
const MODEL_KEYS = ["logistic_regression", "random_forest", "ann"];
const MODEL_COLOR = { logistic_regression: SERIES[0], random_forest: SERIES[1], ann: SERIES[2] };
// GitHub Pages never has the backend, so skip probing it there (avoids 404s in the console).
const C = { overview: null, preds: [], hospitals: [], apiError: null, bundle: null,
  mode: location.hostname.endsWith("github.io") ? "static" : "api" };
// Static copies of the GET endpoints the page uses, for hosts without the backend.
const STATIC = { "/overview": "static-api/overview.json", "/clinical/test-predictions?limit=1000": "static-api/test-predictions.json" };
const pct = (v, d = 1) => (v == null ? "–" : `${fmt(v * 100, d)}%`);
// What each model is, in one plain line.
const PLAIN = { logistic_regression: "A simple weighted score: each answer adds or takes away points.",
  random_forest: "300 small decision trees, each asking yes/no questions, then voting.",
  ann: "A small neural network: layers of simple maths units loosely inspired by the brain.",
  LR: "logistic_regression", RF: "random_forest", ANN: "ann" };
const testN = () => (C.overview ? C.overview.clinical.test : 200);
const rightOf = (acc) => `right for ${Math.round(acc * testN())} of ${testN()} new patients`;

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}${r.status === 503 ? " (pipeline outputs missing)" : ""}`);
  return r.json();
}

// Backend first; if it is not there (404 on GitHub Pages, or no server), use the static copy.
async function getJson(path) {
  if (C.mode === "api") {
    try { return await fetchJson(API + path); } catch (e) { C.mode = "static"; console.info(`No backend (${e.message}); using static files.`); }
  }
  if (!STATIC[path]) throw new Error(`${path} needs the FastAPI backend`);
  return fetchJson(STATIC[path]);
}

async function modelBundle() {
  if (!C.bundle) C.bundle = await fetchJson("static-api/models.json");
  return C.bundle;
}

async function initExtra() {
  try {
    C.hospitals = await new Promise((resolve, reject) => Papa.parse("../data/processed/hospital_list_clean.csv", {
      download: true, header: true, dynamicTyping: true, skipEmptyLines: true, complete: (r) => resolve(r.data), error: reject }));
    C.hospitals.forEach((h) => { h.ward_id = h.ward_id == null ? null : String(h.ward_id); });
  } catch (e) { console.warn("hospital list not loaded", e); }
  try {
    [C.overview, C.preds] = await Promise.all([getJson("/overview"), getJson("/clinical/test-predictions?limit=1000")]);
  } catch (e) {
    C.apiError = e.message;
    console.error(e);
  }
  if (C.apiError) { showApiError(); return; }
  if (C.mode === "static") {
    hideApiDocs();
    // No server to post the plain HTML form to; the in-browser models replace it.
    const srv = document.getElementById("run-server");
    if (srv) srv.hidden = true;
  }
  renderOverviewModels();
  initMonitor();
  renderPredictor();
  // Fetch the browser copy of the models now, so predictions still work if the server stops later.
  modelBundle().catch((e) => console.warn("model bundle not preloaded", e));
}

function showApiError() {
  const msg = `<div class="error-box"><b>The model pages need the FastAPI backend.</b><br>${esc(C.apiError)}<br><br>
    From the project folder run <code>.venv\\Scripts\\uvicorn backend.main:app --port 8050</code> (Windows) or
    <code>.venv/bin/uvicorn backend.main:app --port 8050</code>, then open <a href="http://localhost:8050/dashboard/">http://localhost:8050/dashboard/</a>.</div>`;
  ["ov-models", "predict-result"].forEach((id) => { document.getElementById(id).innerHTML = msg; });
}

/* ---------------- Overview: the three models ---------------- */
function renderOverviewModels() {
  const o = C.overview;
  document.getElementById("ov-clin-src").innerHTML =
    `Trained on records of ${fmt0(o.clinical.records - o.clinical.test)} patients from one hospital in India, then tested on ${o.clinical.test} patients they had never seen (${esc(o.clinical.citation)}). ${pct(o.clinical.positive_rate, 0)} of all patients had heart disease.`;
  document.getElementById("ov-models").innerHTML = o.models.map((m) => `
    <button type="button" class="mcard" style="--c:${MODEL_COLOR[m.key]}" data-go="powerbi">
      <span class="eyebrow">${esc(m.short)} · tested on new patients</span>
      <span class="mname">${esc(m.label)}</span>
      <span class="mplain">${esc(PLAIN[m.key])}</span>
      <span class="mval">${pct(m.accuracy)}<small>${rightOf(m.accuracy)}</small></span>
      <span class="mmeta">Caught ${pct(m.recall)} of the real heart-disease cases · ROC-AUC ${fmt(m.roc_auc, 3)} · F1 ${fmt(m.f1, 3)}</span>
    </button>`).join("") + `
    <button type="button" class="mcard cta" data-go="predict"><span class="eyebrow">Try it</span>
      <span class="mname">Heart risk predictor</span><span class="mmeta">Enter one patient's values and compare all three models. Experimental, for education only.</span>
      <svg class="cta-ecg" viewBox="0 0 400 90" preserveAspectRatio="none" aria-hidden="true"><g class="bs-wave">${(() => {
        const d = `M0 60 ${[0, 100, 200, 300].map(ecgBeat).join(" ")}`;
        return `<path d="${d}"></path><path d="${d}" transform="translate(400 0)"></path>`; })()}</g></svg></button>`;
  document.querySelectorAll("#ov-models [data-go]").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.go)));
}

/* ---------------- Predictor ---------------- */
// Grouped like the sections of a clinical chart.
const GROUPS = [["patient", "Patient"], ["symptoms", "Presenting symptoms"], ["vitals", "Vitals and bloods"],
  ["exercise", "Exercise stress test"], ["ecg", "ECG and imaging"]];
const FIELDS = [
  { k: "age", g: "patient", label: "Age", help: "Years", type: "number", min: 18, max: 100, step: 1 },
  { k: "gender", g: "patient", label: "Sex", help: "As recorded in the dataset", options: { 1: "Male", 0: "Female" } },
  { k: "chestpain", g: "symptoms", label: "Chest pain type", help: "What kind of chest pain the patient described. Angina is chest pain caused by the heart not getting enough blood. Asymptomatic means no chest pain.", options: { 0: "Typical angina", 1: "Atypical angina", 2: "Non-anginal pain", 3: "Asymptomatic" } },
  { k: "restingBP", g: "vitals", label: "Resting blood pressure", help: "Blood pressure while resting: the top number, in mm Hg (80 to 220). About 120 is typical.", type: "number", min: 80, max: 220, step: 1 },
  { k: "serumcholestrol", g: "vitals", label: "Serum cholesterol", help: "Total cholesterol from a blood test, in mg/dl (80 to 700). Leave blank if unknown: the usual value from the training data is used.", type: "number", min: 80, max: 700, step: 1, optional: true },
  { k: "fastingbloodsugar", g: "vitals", label: "Fasting blood sugar > 120 mg/dl", help: "Was blood sugar above 120 mg/dl after not eating overnight? A high value can be a sign of diabetes.", options: { 0: "No", 1: "Yes" } },
  { k: "restingrelectro", g: "ecg", label: "Resting ECG", help: "Result of an ECG, the heart tracing, taken while the patient was resting.", options: { 0: "Normal", 1: "ST-T wave abnormality", 2: "Left ventricular hypertrophy" } },
  { k: "maxheartrate", g: "exercise", label: "Maximum heart rate", help: "Fastest heartbeat reached in the exercise (treadmill) test, in beats per minute (60 to 220).", type: "number", min: 60, max: 220, step: 1 },
  { k: "exerciseangia", g: "symptoms", label: "Exercise-induced angina", help: "Did exercise bring on chest pain?", options: { 0: "No", 1: "Yes" } },
  { k: "oldpeak", g: "exercise", label: "ST depression in exercise (oldpeak)", help: "How far one part of the ECG line, the ST segment, dropped during exercise compared with rest, in mm (0 to 7). Bigger drops can mean the heart muscle is short of blood.", type: "number", min: 0, max: 7, step: 0.1 },
  { k: "slope", g: "exercise", label: "Slope of peak exercise ST segment", help: "The shape of that ST segment at peak exercise. Not recorded for 18% of patients: then the usual value from the training data is used.", optional: true,
    options: [["1", "Upsloping"], ["2", "Flat"], ["3", "Downsloping"], ["", "Not recorded"]] },
  { k: "noofmajorvessels", g: "ecg", label: "Major heart vessels seen on X-ray", help: "How many of the three main heart arteries showed up on an X-ray dye test (fluoroscopy), 0 to 3.", options: { 0: "0", 1: "1", 2: "2", 3: "3" } },
];
const DEFAULTS = { age: 50, gender: 1, chestpain: 0, restingBP: 130, serumcholestrol: "", fastingbloodsugar: 0, restingrelectro: 0, maxheartrate: 150, exerciseangia: 0, oldpeak: 1.0, slope: 1, noofmajorvessels: 0 };

function renderPredictor() {
  const form = document.getElementById("predict-form");
  const field = (f) => `<label class="field"><span class="flabel">${f.label}${f.optional ? " <i>optional</i>" : ""}</span>
    ${f.options ? `<select name="${f.k}">${(Array.isArray(f.options) ? f.options : Object.entries(f.options)).map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>`
      : `<input name="${f.k}" type="number" inputmode="decimal" min="${f.min}" max="${f.max}" step="${f.step}" ${f.optional ? "" : "required"}>`}
    <span class="fhelp">${f.help}</span></label>`;
  form.innerHTML = GROUPS.map(([g, title]) => `<fieldset class="fgroup"><legend>${title}</legend>
    <div class="fgrid">${FIELDS.filter((f) => f.g === g).map(field).join("")}</div></fieldset>`).join("");
  setForm(DEFAULTS);
  form.addEventListener("submit", (e) => {
    if (e.submitter && e.submitter.id === "run-server") {
      if (!validate()) e.preventDefault();
      return; // native POST to /predict renders a server-side result page
    }
    e.preventDefault();
    runPrediction();
  });
  form.addEventListener("input", () => {
    C.preset = null; document.getElementById("preset-note").textContent = ""; updateMonitor();
    // A result on screen no longer matches the chart: mark it stale until the models run again.
    const out = document.getElementById("predict-result");
    if (out.querySelector(".verdict")) out.classList.add("stale");
  });
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    const want = Number(b.dataset.preset);
    const pool = C.preds.filter((p) => p.actual === want);
    const p = pool[Math.floor(Math.random() * pool.length)];
    setForm(Object.fromEntries(FIELDS.map((f) => [f.k, p[f.k] == null ? "" : p[f.k]])));
    C.preset = p;
    updateMonitor();
    document.getElementById("preset-note").innerHTML = `Filled from real test patient <b>${p.patientid}</b>, who ${p.actual ? "did have heart disease" : "did not have heart disease"}. The models never saw this patient while learning, so you can check whether they get it right.`;
    runPrediction();
  }));
}

function setForm(v) {
  const form = document.getElementById("predict-form");
  FIELDS.forEach((f) => { form.elements[f.k].value = v[f.k] ?? ""; });
  C.preset = null;
  document.getElementById("preset-note").textContent = "";
  updateMonitor();
}

/* ---------------- Bedside monitor: mirrors the form; the ECG runs at the entered heart rate ---------------- */
function ecgBeat(x0) {
  return `L${x0 + 10} 60 Q${x0 + 16} 51 ${x0 + 22} 60 L${x0 + 30} 60 L${x0 + 33} 67 L${x0 + 37} 10 L${x0 + 41} 80 ` +
    `L${x0 + 45} 60 L${x0 + 56} 60 Q${x0 + 64} 44 ${x0 + 72} 60 L${x0 + 100} 60`;
}

function initMonitor() {
  const wave = document.getElementById("bs-wave");
  if (!wave) return;
  const d = `M0 60 ${[0, 100, 200, 300].map(ecgBeat).join(" ")}`;
  wave.innerHTML = `<path d="${d}"></path><path d="${d}" transform="translate(400 0)"></path>`;
}

function updateMonitor() {
  const form = document.getElementById("predict-form"), mon = document.getElementById("bedside");
  if (!form || !mon || !form.elements.maxheartrate) return;
  const val = (k) => form.elements[k].value.trim();
  const num = (k, lo, hi) => { const n = Number(val(k)); return val(k) !== "" && Number.isFinite(n) && n >= lo && n <= hi ? n : null; };
  const hr = num("maxheartrate", 60, 220), bp = num("restingBP", 80, 220), chol = num("serumcholestrol", 80, 700),
    st = num("oldpeak", 0, 7), age = num("age", 18, 100);
  const set = (id, v) => { document.getElementById(id).textContent = v; };
  set("bs-hr", hr ?? "--"); set("bs-bp", bp ?? "--"); set("bs-chol", chol ?? "median");
  set("bs-st", st == null ? "--" : st.toFixed(1)); set("bs-age", age ?? "--");
  // Four beats scroll past per loop, so one loop lasts 4 x 60 / bpm seconds.
  const bpm = hr || 72;
  mon.style.setProperty("--loop", `${(4 * 60) / bpm}s`);
  mon.style.setProperty("--beat", `${60 / bpm}s`);
  mon.classList.toggle("flat", hr == null);
  const sex = form.elements.gender.value === "1" ? "M" : "F";
  set("bs-id", C.preset ? `Test patient ${C.preset.patientid} · ${age ?? "?"} ${sex}` : `Manual entry · ${age ?? "?"} ${sex}`);
  document.getElementById("bs-id").classList.toggle("tagged", !!C.preset);
}

function validate() {
  const form = document.getElementById("predict-form");
  const errs = [];
  FIELDS.forEach((f) => {
    const el = form.elements[f.k];
    el.classList.remove("bad");
    if (f.options) return;
    const raw = el.value.trim();
    if (raw === "" && f.optional) return;
    const n = Number(raw);
    if (raw === "" || !Number.isFinite(n) || n < f.min || n > f.max) { errs.push(`${f.label} must be between ${f.min} and ${f.max}`); el.classList.add("bad"); }
  });
  document.getElementById("form-error").textContent = errs.join(" · ");
  return !errs.length;
}

async function runPrediction() {
  if (!validate()) return;
  const form = document.getElementById("predict-form");
  const body = Object.fromEntries(FIELDS.map((f) => {
    const raw = form.elements[f.k].value.trim();
    return [f.k, raw === "" ? null : Number(raw)];
  }));
  const out = document.getElementById("predict-result");
  out.classList.remove("stale");
  out.classList.add("busy");
  try {
    const j = C.mode === "api" ? await predictOnServer(body) : null;
    out.innerHTML = resultHtml(j || ModelRuntime.predict(await modelBundle(), body));
    // On narrow screens the result sits below the long form, so bring it into view.
    if (matchMedia("(max-width: 960px)").matches && !C.preset) out.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    const offline = e instanceof TypeError && /fetch/i.test(e.message);
    out.innerHTML = `<div class="error-box">Prediction failed: ${offline
      ? "the page cannot reach the server that loaded it. If you started it with uvicorn or http.server, that server has stopped. Start it again and reload this page."
      : esc(e.message)}</div>`;
  } finally { out.classList.remove("busy"); }
}

// The server went away (or never existed): run the models in the browser and hide the server-only form button.
// The FastAPI docs page only exists when the Python server runs, so hide every link to it otherwise.
function hideApiDocs() { document.querySelectorAll('a[href="/api/docs"]').forEach((a) => { a.hidden = true; }); }

function goStatic() {
  C.mode = "static";
  hideApiDocs();
  const srv = document.getElementById("run-server");
  if (srv) srv.hidden = true;
}

// Returns null when there is no backend to answer, so the caller can run the models in the browser instead.
async function predictOnServer(body) {
  let r;
  try {
    r = await fetch(`${API}/predict`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) { goStatic(); return null; }
  if ([404, 405, 501].includes(r.status)) { goStatic(); return null; }
  const j = await r.json();
  if (!r.ok) throw new Error(Array.isArray(j.detail) ? j.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ") : j.detail);
  return j;
}

function resultHtml(j) {
  const n = j.models_predicting_disease;
  const agree = n === 0 || n === 3;
  const keyOf = { LR: "logistic_regression", RF: "random_forest", ANN: "ann" };
  const actual = C.preset ? `<div class="actual">What really happened: this test patient <b>${C.preset.actual ? "did have heart disease" : "did not have heart disease"}</b>, so you can see whether the models got it right.</div>` : "";
  return `
    <div class="verdict ${n >= 2 ? "pos" : "neg"}"><span class="badge">${n} of 3 models</span>
      <span>${n >= 2 ? "indicate heart disease" : "indicate no heart disease"} at the ${pct(j.threshold, 0)} threshold</span></div>
    <p class="plain-sum"><b>In simple words:</b> ${n === 3 ? "all three models think" : n === 0 ? "none of the three models think" : `${n} of the 3 models think`}
      these test results look like those of past patients who had heart disease. Each percentage below is that model's estimated
      chance of heart disease; above ${pct(j.threshold, 0)} counts as "indicated". This is a learning tool, not a diagnosis.</p>
    ${actual}
    ${j.predictions.map((p) => `<div class="mres" style="--c:${MODEL_COLOR[keyOf[p.model]]}">
      <div class="mres-head"><span class="eyebrow">${esc(p.label)}</span><span class="pill-out ${p.predicted_class ? "pos" : "neg"}">${esc(p.predicted_label)}</span></div>
      <p class="mplain">${esc(PLAIN[PLAIN[p.model]])}</p>
      <div class="mres-row"><span class="big">${pct(p.probability)}</span><span class="hint">estimated chance of heart disease · ${rightOf(p.test_accuracy)}</span></div>
      <div class="gauge" role="img" aria-label="${pct(p.probability)}"><i style="width:${(p.probability * 100).toFixed(1)}%"></i><b style="left:${j.threshold * 100}%"></b></div>
      <div class="ticks"><span>0%</span><span>${pct(j.threshold, 0)} cut-off</span><span>100%</span></div>
    </div>`).join("")}
    <div class="uncert"><b>${agree ? "The models agree." : "The models disagree."}</b>
      On average they give ${pct(j.mean_probability)}; the highest and lowest are ${fmt(j.probability_spread * 100, 1)} points apart.
      ${agree ? "Agreement only means three models fitted to the same data learned similar patterns; it does not make the result certain." : "Disagreement is a sign this record sits near the models' decision boundary."}
      ${j.imputed_fields.length ? `<br>Not entered, so filled from the training data (median for numbers, most common value for categories): ${j.imputed_fields.join(", ")}.` : ""}</div>
    <p class="disc">${esc(j.disclaimer)}</p>
    ${C.mode === "static" ? `<p class="hint">Computed in your browser from the same three trained models (exported to static-api/models.json), because this site has no Python server.</p>` : ""}`;
}

/* ---------------- Hospitals list (ward panel) ---------------- */
function hospitalRows(rows) {
  return `<thead><tr><th class="left">Hospital</th><th class="left">Ownership</th><th>Beds</th></tr></thead><tbody>
    ${rows.map((h) => `<tr><td class="left wrapcell">${esc(h.hospital_name)}${h.matched_facility_id ? ' <span class="tag">on map</span>' : ""}</td>
      <td class="left">${esc(h.ownership_type)}</td><td>${h.beds == null ? '<span class="hint">not listed</span>' : fmt0(h.beds)}</td></tr>`).join("")}</tbody>`;
}

// Extra section for the ward drawer (called from openWard in app.js).
function wardHospitalList(id) {
  const rows = C.hospitals.filter((h) => h.ward_id === id);
  if (!rows.length) return `<h3>Hospitals list</h3><p class="hint">The hospitals CSV has no rows for this ward.</p>`;
  const beds = rows.reduce((a, h) => a + (h.beds || 0), 0);
  return `<h3>Hospitals list (${rows.length})</h3><p class="hint">From the MCGM hospitals CSV, including private and trust hospitals. ${fmt0(beds)} listed beds; bed counts are not staffing or availability.</p>
    <table>${hospitalRows(rows)}</table>`;
}
