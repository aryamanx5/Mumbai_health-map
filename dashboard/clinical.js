/* Added: the model cards on the overview, the heart risk predictor and the hospitals list in the ward panel.
   Uses the helpers in app.js (S, fmt, esc, showPage, openWard, ...). Model results come from the FastAPI backend
   (/api); the hospital list is read from the pipeline's files directly. Charts are in the Power BI report. */
"use strict";

const API = "/api";
const MODEL_KEYS = ["logistic_regression", "random_forest", "ann"];
const MODEL_COLOR = { logistic_regression: SERIES[0], random_forest: SERIES[1], ann: SERIES[2] };
const C = { overview: null, preds: [], hospitals: [], apiError: null };
const pct = (v, d = 1) => (v == null ? "–" : `${fmt(v * 100, d)}%`);

async function getJson(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${API}${path}: HTTP ${r.status}${r.status === 503 ? " (pipeline outputs missing)" : ""}`);
  return r.json();
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
  renderOverviewModels();
  renderPredictor();
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
    `${fmt0(o.clinical.records)} patients from one hospital in India (${esc(o.clinical.citation)}); ${pct(o.clinical.positive_rate, 0)} with heart disease. Test set: ${o.clinical.test} patients.`;
  document.getElementById("ov-models").innerHTML = o.models.map((m) => `
    <button type="button" class="mcard" style="--c:${MODEL_COLOR[m.key]}" data-go="powerbi">
      <span class="eyebrow">${esc(m.short)} · test set</span>
      <span class="mname">${esc(m.label)}</span>
      <span class="mval">${pct(m.accuracy)}<small>accuracy</small></span>
      <span class="mmeta">ROC-AUC ${fmt(m.roc_auc, 3)} · F1 ${fmt(m.f1, 3)} · recall ${pct(m.recall)}</span>
    </button>`).join("") + `
    <button type="button" class="mcard cta" data-go="predict"><span class="eyebrow">Try it</span>
      <span class="mname">Heart risk predictor</span><span class="mmeta">Enter one patient's values and compare all three models. Experimental, for education only.</span></button>`;
  document.querySelectorAll("#ov-models [data-go]").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.go)));
}

/* ---------------- Predictor ---------------- */
const FIELDS = [
  { k: "age", label: "Age", help: "Years", type: "number", min: 18, max: 100, step: 1 },
  { k: "gender", label: "Sex", help: "As recorded in the dataset", options: { 1: "Male", 0: "Female" } },
  { k: "chestpain", label: "Chest pain type", help: "Type of chest pain reported", options: { 0: "Typical angina", 1: "Atypical angina", 2: "Non-anginal pain", 3: "Asymptomatic" } },
  { k: "restingBP", label: "Resting blood pressure", help: "Systolic, mm Hg (80–220)", type: "number", min: 80, max: 220, step: 1 },
  { k: "serumcholestrol", label: "Serum cholesterol", help: "mg/dl (80–700). Leave blank if unknown: the training median is used", type: "number", min: 80, max: 700, step: 1, optional: true },
  { k: "fastingbloodsugar", label: "Fasting blood sugar > 120 mg/dl", help: "Raised fasting glucose", options: { 0: "No", 1: "Yes" } },
  { k: "restingrelectro", label: "Resting ECG", help: "Electrocardiogram at rest", options: { 0: "Normal", 1: "ST-T wave abnormality", 2: "Left ventricular hypertrophy" } },
  { k: "maxheartrate", label: "Maximum heart rate", help: "Highest rate in the exercise test, bpm (60–220)", type: "number", min: 60, max: 220, step: 1 },
  { k: "exerciseangia", label: "Exercise-induced angina", help: "Chest pain brought on by exercise", options: { 0: "No", 1: "Yes" } },
  { k: "oldpeak", label: "ST depression (oldpeak)", help: "ST drop in exercise vs rest, mm (0–7)", type: "number", min: 0, max: 7, step: 0.1 },
  { k: "slope", label: "Slope of peak exercise ST segment", help: "Shape of the ST segment at peak exercise", options: { 1: "Upsloping", 2: "Flat", 3: "Downsloping" } },
  { k: "noofmajorvessels", label: "Major vessels (fluoroscopy)", help: "Vessels coloured by fluoroscopy, 0–3", options: { 0: "0", 1: "1", 2: "2", 3: "3" } },
];
const DEFAULTS = { age: 50, gender: 1, chestpain: 0, restingBP: 130, serumcholestrol: "", fastingbloodsugar: 0, restingrelectro: 0, maxheartrate: 150, exerciseangia: 0, oldpeak: 1.0, slope: 1, noofmajorvessels: 0 };

function renderPredictor() {
  const form = document.getElementById("predict-form");
  form.innerHTML = FIELDS.map((f) => `<label class="field"><span class="flabel">${f.label}${f.optional ? " <i>optional</i>" : ""}</span>
    ${f.options ? `<select name="${f.k}">${Object.entries(f.options).map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>`
      : `<input name="${f.k}" type="number" inputmode="decimal" min="${f.min}" max="${f.max}" step="${f.step}" ${f.optional ? "" : "required"}>`}
    <span class="fhelp">${f.help}</span></label>`).join("");
  setForm(DEFAULTS);
  form.addEventListener("submit", (e) => {
    if (e.submitter && e.submitter.id === "run-server") {
      if (!validate()) e.preventDefault();
      return; // native POST to /predict renders a server-side result page
    }
    e.preventDefault();
    runPrediction();
  });
  form.addEventListener("input", () => { C.preset = null; document.getElementById("preset-note").textContent = ""; });
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    const want = Number(b.dataset.preset);
    const pool = C.preds.filter((p) => p.actual === want);
    const p = pool[Math.floor(Math.random() * pool.length)];
    setForm(Object.fromEntries(FIELDS.map((f) => [f.k, p[f.k] == null ? "" : p[f.k]])));
    C.preset = p;
    document.getElementById("preset-note").innerHTML = `Filled from test patient <b>${p.patientid}</b> (actual: ${p.actual ? "heart disease" : "no heart disease"}). The models never saw this patient during training.`;
    runPrediction();
  }));
}

function setForm(v) {
  const form = document.getElementById("predict-form");
  FIELDS.forEach((f) => { form.elements[f.k].value = v[f.k] ?? ""; });
  C.preset = null;
  document.getElementById("preset-note").textContent = "";
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
  out.classList.add("busy");
  try {
    const r = await fetch(`${API}/predict`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(Array.isArray(j.detail) ? j.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ") : j.detail);
    out.innerHTML = resultHtml(j);
  } catch (e) {
    out.innerHTML = `<div class="error-box">Prediction failed: ${esc(e.message)}</div>`;
  } finally { out.classList.remove("busy"); }
}

function resultHtml(j) {
  const n = j.models_predicting_disease;
  const agree = n === 0 || n === 3;
  const keyOf = { LR: "logistic_regression", RF: "random_forest", ANN: "ann" };
  const actual = C.preset ? `<div class="actual">Recorded outcome for this test patient: <b>${C.preset.actual ? "heart disease" : "no heart disease"}</b></div>` : "";
  return `
    <div class="verdict ${n >= 2 ? "pos" : "neg"}"><span class="badge">${n} of 3 models</span>
      <span>${n >= 2 ? "indicate heart disease" : "indicate no heart disease"} at the ${pct(j.threshold, 0)} threshold</span></div>
    ${actual}
    ${j.predictions.map((p) => `<div class="mres" style="--c:${MODEL_COLOR[keyOf[p.model]]}">
      <div class="mres-head"><span class="eyebrow">${esc(p.label)}</span><span class="pill-out ${p.predicted_class ? "pos" : "neg"}">${esc(p.predicted_label)}</span></div>
      <div class="mres-row"><span class="big">${pct(p.probability)}</span><span class="hint">probability of the heart-disease class · test ROC-AUC ${fmt(p.test_roc_auc, 3)}</span></div>
      <div class="gauge" role="img" aria-label="${pct(p.probability)}"><i style="width:${(p.probability * 100).toFixed(1)}%"></i><b style="left:${j.threshold * 100}%"></b></div>
      <div class="ticks"><span>0%</span><span>threshold ${pct(j.threshold, 0)}</span><span>100%</span></div>
    </div>`).join("")}
    <div class="uncert"><b>${agree ? "The models agree." : "The models disagree."}</b>
      Mean probability ${pct(j.mean_probability)}, spread ${fmt(j.probability_spread * 100, 1)} points between the lowest and highest model.
      ${agree ? "Agreement only means three models fitted to the same data learned similar patterns; it does not make the result certain." : "Disagreement is a sign this record sits near the models' decision boundary."}
      ${j.imputed_fields.length ? `<br>Imputed with the training median: ${j.imputed_fields.join(", ")}.` : ""}</div>
    <p class="disc">${esc(j.disclaimer)}</p>`;
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
