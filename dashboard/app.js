/* Mumbai ward healthcare dashboard: reads the pipeline's Power BI-ready CSVs. Charts and maps live in the Power BI
   report (powerbi/MumbaiHealth.pbip), which the "Power BI dashboard" tab embeds. */
"use strict";

const DATA = "../powerbi/data/";
const CATS = ["dispensary", "uphc", "public_hospital", "maternity_hospital"];
const CAT_LABEL = { dispensary: "Dispensary", uphc: "UPHC", public_hospital: "Public hospital", maternity_hospital: "Maternity home" };
// Reference categorical palette, fixed slot order (never cycled).
// Dark-surface steps of the validated reference palette.
const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500"];
const CAT_COLOR = Object.fromEntries(CATS.map((c, i) => [c, SERIES[i]]));
const CLUSTER_COLOR = { 1: SERIES[0], 2: SERIES[1], 3: SERIES[2], 4: SERIES[3] };

const S = { wards: [], facilities: [], byWard: {}, cityRate: 0 };
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? "–" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmt0 = (v) => fmt(v, 0);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function loadCsv(name) {
  return new Promise((resolve, reject) =>
    Papa.parse(DATA + name, { download: true, header: true, dynamicTyping: true, skipEmptyLines: true,
      complete: (r) => resolve(r.data), error: reject }));
}

async function init() {
  try {
    const [wards, facilities] = await Promise.all([loadCsv("dim_ward.csv"), loadCsv("fact_facility.csv")]);
    if (!wards.length) throw new Error("dim_ward.csv is empty. Run run_pipeline.py first.");
    wards.forEach((w) => { w.ward_id = String(w.ward_id); });
    facilities.forEach((f) => { f.ward_id = String(f.ward_id); });
    Object.assign(S, { wards, facilities });
    S.byWard = Object.fromEntries(wards.map((w) => [w.ward_id, w]));
    const pop = sum(wards, "population_2011");
    S.cityRate = sum(wards, "total_distinct_public_facilities") / pop * 1e5;

    renderOverview();
    renderPowerBI();
    await initExtra(); // model cards and the heart risk predictor (clinical.js)
    document.getElementById("loading").hidden = true;
    routeFromHash();
  } catch (e) {
    document.getElementById("loading").hidden = true;
    const el = document.getElementById("error");
    el.hidden = false;
    el.textContent = "Could not load the pipeline outputs.\n\n" + e.message +
      "\n\nServe the project root over HTTP (see README) and make sure run_pipeline.py has been run.";
    console.error(e);
  }
}

// Animate numbers from 0 to their final text, keeping the final formatting (commas, decimals).
function countUp(nodes) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  nodes.forEach((el) => {
    const final = el.dataset.count, target = parseFloat(final.replace(/,/g, ""));
    if (!Number.isFinite(target)) return;
    const dec = (final.split(".")[1] || "").length, t0 = performance.now(), dur = 1100;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
      el.textContent = k < 1 ? fmt(target * e, dec) : final;
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

const sum = (rows, k) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);

/* ---------------- navigation ---------------- */
const PAGES = ["overview", "predict", "powerbi"];
function showPage(id) {
  if (!PAGES.includes(id)) id = "overview";
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `page-${id}`; });
  const page = document.getElementById(`page-${id}`);
  [...page.querySelectorAll(":scope > *, .grid > *, .kpis > *")].forEach((el, i) => el.style.setProperty("--i", Math.min(i, 10)));
  page.classList.remove("entering"); void page.offsetWidth; page.classList.add("entering");
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.page === id));
  history.replaceState(null, "", `#${id}`);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));
document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); showPage(b.dataset.go); }));
// "#ward=R/S" opens the overview with that ward's detail panel (used by the landing page links).
function routeFromHash() {
  const h = decodeURIComponent(location.hash.replace("#", ""));
  if (h.startsWith("ward=")) { showPage("overview"); openWard(h.slice(5)); return; }
  showPage(h || "overview");
}
window.addEventListener("hashchange", () => { if (S.wards.length) routeFromHash(); });

const wardTitle = (id) => { const w = S.byWard[id]; return w.ward_name === id ? `Ward ${id}` : `Ward ${id} (${w.ward_name})`; };

/* ---------------- Page 1 ---------------- */
function renderOverview() {
  const sites = sum(S.wards, "total_distinct_public_facilities");
  const records = S.facilities.length;
  const pop = sum(S.wards, "population_2011");
  const kpis = [
    ["Distinct facility sites", fmt0(sites), "physical sites after co-location"],
    ["Facility records", fmt0(records), "dispensary · UPHC · hospital · maternity"],
    ["Population (Census 2011)", fmt0(pop), "24 wards"],
    ["Sites per 100,000 residents", fmt(S.cityRate), `ward range ${fmt(min("facilities_per_100k"))} – ${fmt(max("facilities_per_100k"))}`],
  ];
  document.getElementById("kpis").innerHTML = kpis.map(([l, v, f]) =>
    `<div class="kpi"><div class="label">${l}</div><div class="value" data-count="${v}">${v}</div><div class="foot">${f}</div></div>`).join("");
  countUp(document.querySelectorAll("#kpis .value"));

  const byRate = [...S.wards].sort((a, b) => a.facilities_per_100k - b.facilities_per_100k);
  const byGap = [...S.wards].sort((a, b) => b.population_facility_share_gap - a.population_facility_share_gap);
  const island = S.wards.filter((w) => w.census_district === "Mumbai");
  const suburb = S.wards.filter((w) => w.census_district !== "Mumbai");
  const rate = (rows) => sum(rows, "total_distinct_public_facilities") / sum(rows, "population_2011") * 1e5;
  const hosp = [...S.wards].sort((a, b) => b.public_hospital_count - a.public_hospital_count);
  const nHosp = S.facilities.filter((f) => f.category === "public_hospital").length;
  const obs = [
    `Lowest provision per resident: ${byRate.slice(0, 3).map((w) => `<b>${w.ward_id}</b> (${fmt(w.facilities_per_100k)})`).join(", ")} sites per 100k. Highest: ${byRate.slice(-3).reverse().map((w) => `<b>${w.ward_id}</b> (${fmt(w.facilities_per_100k)})`).join(", ")}.`,
    `Island-city wards (A–G/N) have <b>${fmt(rate(island))}</b> sites per 100k against <b>${fmt(rate(suburb))}</b> in the suburban wards.`,
    `${byGap.filter((w) => w.population_facility_share_gap > 0).length} of 24 wards have a larger share of population than of listed sites. Largest gaps: ${byGap.slice(0, 3).map((w) => `<b>${w.ward_id}</b> (+${fmt(w.population_facility_share_gap)} pp)`).join(", ")}.`,
    `Public hospitals are concentrated in ${hosp[0].ward_id} and ${hosp[1].ward_id}, which hold ${hosp[0].public_hospital_count + hosp[1].public_hospital_count} of ${nHosp} hospital records.`,
    `Caveat: population is from 2011, and counts ignore capacity, staffing and private provision. These are distribution indicators, not proof that a ward is underserved.`,
  ];
  document.getElementById("observations").innerHTML = obs.map((o) => `<li>${o}</li>`).join("");

  const pick = document.getElementById("ward-pick");
  pick.innerHTML += S.wards.map((w) => `<option value="${esc(w.ward_id)}">${esc(wardTitle(w.ward_id))}</option>`).join("");
  pick.addEventListener("change", () => { if (pick.value) openWard(pick.value); });
}
const min = (k) => Math.min(...S.wards.map((w) => w[k]));
const max = (k) => Math.max(...S.wards.map((w) => w[k]));

function clusterPill(c) { return `<span class="pill" style="background:${CLUSTER_COLOR[c]}">${c}</span>`; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }

/* ---------------- Power BI report ---------------- */
function renderPowerBI() {
  const cfg = window.POWERBI_REPORT || {};
  const url = String(cfg.embedUrl || "").trim();
  const ok = /^https:\/\/app\.powerbi\.com\//.test(url);
  document.getElementById("pbi-setup").hidden = ok;
  document.getElementById("pbi-frame").innerHTML = ok
    ? `<iframe title="Mumbai Health Power BI report" src="${esc(url)}" allowfullscreen></iframe>`
    : `<div class="empty"><p>The Power BI report is not connected yet. Publish it, then paste its embed link into
       <code>dashboard/powerbi-config.js</code> (steps below).</p></div>`;
  document.getElementById("pbi-frame").classList.toggle("unset", !ok);
  const open = document.getElementById("pbi-open");
  const link = String(cfg.reportUrl || url).trim();
  if (/^https:\/\/app\.powerbi\.com\//.test(link)) { open.href = link; open.hidden = false; }
}

/* ---------------- Ward detail drawer (drill-through) ---------------- */
function openWard(id) {
  const w = S.byWard[id];
  if (!w) return;
  const fac = S.facilities.filter((f) => f.ward_id === id).sort((a, b) => CATS.indexOf(a.category) - CATS.indexOf(b.category) || a.facility_name.localeCompare(b.facility_name));
  const rankLow = [...S.wards].sort((a, b) => a.facilities_per_100k - b.facilities_per_100k).findIndex((x) => x.ward_id === id) + 1;
  const stat = (l, v) => `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div></div>`;
  document.getElementById("drawer-body").innerHTML = `
    <h2>${wardTitle(id)}</h2>
    <p class="hint">${w.census_district === "Mumbai" ? "Island city" : "Suburban"} · ${fmt(w.area_km2, 1)} km² · cluster ${clusterPill(w.cluster_label)} ${esc(w.cluster_name)}</p>
    <div class="stats">
      ${stat("Population (2011)", fmt0(w.population_2011))}
      ${stat("Distinct sites", fmt0(w.total_distinct_public_facilities))}
      ${stat("Sites per 100k", `${fmt(w.facilities_per_100k)} <span class="hint">(${rankLow}/24 low→high)</span>`)}
      ${stat("Residents per site", fmt0(w.population_per_facility))}
      ${stat("Population share", `${fmt(w.population_share_pct)}%`)}
      ${stat("Facility share", `${fmt(w.facility_share_pct)}%`)}
    </div>
    <p class="hint">Share gap: <b>${w.population_facility_share_gap > 0 ? "+" : ""}${fmt(w.population_facility_share_gap)} pp</b>
      ${w.population_facility_share_gap > 0 ? "(larger share of population than of listed sites)" : "(larger share of listed sites than of population)"}</p>
    <h3>Facilities (${fac.length} records)</h3>
    <table><thead><tr><th>Name</th><th>Category</th></tr></thead><tbody>
      ${fac.map((f) => `<tr><td>${esc(f.facility_name)}${String(f.assignment_check).includes("review") ? '<div class="flag">location disagrees with ward, flagged for review</div>' : ""}${f.latitude ? "" : '<div class="flag">no coordinates</div>'}</td>
        <td><span class="dot" style="background:${CAT_COLOR[f.category]}"></span> ${CAT_LABEL[f.category]}</td></tr>`).join("")}
    </tbody></table>
    ${typeof wardHospitalList === "function" ? wardHospitalList(id) : ""}`;
  document.getElementById("drawer").classList.add("open");
  document.getElementById("drawer").setAttribute("aria-hidden", "false");
  document.getElementById("scrim").hidden = false;
}
function closeWard() {
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawer").setAttribute("aria-hidden", "true");
  document.getElementById("scrim").hidden = true;
}
document.getElementById("drawer-close").addEventListener("click", closeWard);
document.getElementById("scrim").addEventListener("click", closeWard);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeWard(); });

init();
