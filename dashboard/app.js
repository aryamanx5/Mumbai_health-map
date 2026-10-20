/* Mumbai ward healthcare dashboard: reads the pipeline's Power BI-ready CSVs and ward GeoJSON. */
"use strict";

const DATA = "../powerbi/data/";
const GEO = "../data/processed/ward_boundaries.geojson";
const CATS = ["dispensary", "uphc", "public_hospital", "maternity_hospital"];
const CAT_LABEL = { dispensary: "Dispensary", uphc: "UPHC", public_hospital: "Public hospital", maternity_hospital: "Maternity home" };
// Reference categorical palette, fixed slot order (never cycled).
// Dark-surface steps of the validated reference palette.
const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500"];
const CAT_COLOR = Object.fromEntries(CATS.map((c, i) => [c, SERIES[i]]));
const CLUSTER_COLOR = { 1: SERIES[0], 2: SERIES[1], 3: SERIES[2], 4: SERIES[3] };
// Sequential ramp for the dark basemap: dim to bright, so higher provision reads brighter.
const SEQ = ["#184f95", "#256abf", "#3987e5", "#5598e7", "#86b6ef", "#cde2fb"];

const S = { wards: [], facilities: [], clusters: [], kEval: [], geo: null, byWard: {}, cityRate: 0, charts: {}, maps: {} };
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
    const [wards, facilities, clusters, kEval, geo] = await Promise.all([
      loadCsv("dim_ward.csv"), loadCsv("fact_facility.csv"), loadCsv("dim_cluster.csv"),
      loadCsv("ml_k_evaluation.csv"), fetch(GEO).then((r) => { if (!r.ok) throw new Error(`${GEO}: HTTP ${r.status}`); return r.json(); }),
    ]);
    if (!wards.length) throw new Error("dim_ward.csv is empty. Run run_pipeline.py first.");
    wards.forEach((w) => { w.ward_id = String(w.ward_id); });
    facilities.forEach((f) => { f.ward_id = String(f.ward_id); });
    Object.assign(S, { wards, facilities, clusters, kEval, geo });
    S.byWard = Object.fromEntries(wards.map((w) => [w.ward_id, w]));
    const pop = sum(wards, "population_2011");
    S.cityRate = sum(wards, "total_distinct_public_facilities") / pop * 1e5;

    setupChartDefaults();
    renderOverview();
    setupWardFilters();
    renderWards();
    renderClusters();
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
function showPage(id) {
  if (!["overview", "wards", "clusters"].includes(id)) id = "overview";
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `page-${id}`; });
  const page = document.getElementById(`page-${id}`);
  [...page.querySelectorAll(":scope > *, .grid > *, .kpis > *, .cluster-cards > *")].forEach((el, i) => el.style.setProperty("--i", Math.min(i, 10)));
  page.classList.remove("entering"); void page.offsetWidth; page.classList.add("entering");
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.page === id));
  history.replaceState(null, "", `#${id}`);
  // Charts and maps built while their page was hidden have zero width; size them now that it is visible.
  // Run immediately (layout is current once `hidden` is removed) and again shortly after, without relying
  // on requestAnimationFrame, which background tabs pause.
  const sizeCharts = () => Object.values(S.charts).forEach((c) => {
    // stop() first: Chart.js defers resize() while an animation is running, which left these charts 0 px wide.
    if (page.contains(c.canvas)) { c.stop(); c.resize(); c.update(); }
  });
  sizeCharts();
  setTimeout(() => Object.values(S.maps).forEach((m) => {
    m.invalidateSize();
    if (m._wardBounds) m.fitBounds(m._wardBounds, { padding: [8, 8] });
  }), 50);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));
// "#ward=R/S" opens the Ward analysis page with that ward's detail panel (used by the landing page links).
function routeFromHash() {
  const h = decodeURIComponent(location.hash.replace("#", ""));
  if (h.startsWith("ward=")) { showPage("wards"); openWard(h.slice(5)); return; }
  showPage(h || "overview");
}
window.addEventListener("hashchange", () => { if (S.wards.length) routeFromHash(); });

/* ---------------- chart helpers ---------------- */
function setupChartDefaults() {
  Chart.defaults.font.family = "Barlow, -apple-system, Segoe UI, Helvetica, Arial, sans-serif";
  Chart.defaults.font.size = 13;
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--line");
  Chart.defaults.animation = { duration: 800, easing: "easeOutQuart" };
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) Chart.defaults.animation = false;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.tooltip.backgroundColor = "#2b2e32";
  Chart.defaults.plugins.tooltip.titleFont = { family: "Barlow Condensed", size: 16, weight: "700" };
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.maintainAspectRatio = false;
}

// Draws a dashed vertical (or diagonal) reference line with a label.
const refLine = {
  id: "refLine",
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || opts.value === undefined) return;
    const { ctx, chartArea: a, scales } = chart;
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = css("--muted");
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (opts.slope !== undefined) {
      const x0 = scales.x.min, x1 = scales.x.max;
      ctx.moveTo(scales.x.getPixelForValue(x0), scales.y.getPixelForValue(x0 * opts.slope));
      ctx.lineTo(scales.x.getPixelForValue(x1), scales.y.getPixelForValue(x1 * opts.slope));
    } else {
      const x = scales.x.getPixelForValue(opts.value);
      ctx.moveTo(x, a.top); ctx.lineTo(x, a.bottom);
      ctx.setLineDash([]);
      ctx.fillStyle = css("--muted");
      ctx.font = "600 12px Barlow, sans-serif";
      ctx.fillText(opts.label || "", x + 4, a.top + 10);
    }
    ctx.stroke();
    ctx.restore();
  },
};
Chart.register(refLine);

function makeChart(id, config) {
  if (S.charts[id]) S.charts[id].destroy();
  S.charts[id] = new Chart(document.getElementById(id), config);
  return S.charts[id];
}

function hbar(id, rows, valueKey, { color, label, fmtV = (v) => fmt(v), ref, onClick, colorFn } = {}) {
  const wrap = document.getElementById(id).parentElement;
  wrap.style.height = `${Math.max(260, rows.length * 22 + 50)}px`;
  return makeChart(id, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.ward_id),
      datasets: [{ label, data: rows.map((r) => r[valueKey]),
        backgroundColor: colorFn ? rows.map(colorFn) : color, borderRadius: 4, borderSkipped: false, barPercentage: 0.75, categoryPercentage: 0.9 }],
    },
    options: {
      indexAxis: "y", 
      plugins: { legend: { display: false }, refLine: ref,
        tooltip: { callbacks: { title: (it) => wardTitle(rows[it[0].dataIndex].ward_id), label: (it) => `${label}: ${fmtV(it.raw)}` } } },
      scales: { x: { grid: { color: css("--line") } }, y: { grid: { display: false }, ticks: { autoSkip: false } } },
      onClick: (_e, els) => { if (els.length && onClick) onClick(rows[els[0].index].ward_id); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
    },
  });
}

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

  const counts = CATS.map((c) => S.facilities.filter((f) => f.category === c).length);
  makeChart("chart-category", {
    type: "bar",
    data: { labels: CATS.map((c) => CAT_LABEL[c]), datasets: [{ data: counts, backgroundColor: CATS.map((c) => CAT_COLOR[c]), borderRadius: 4, barPercentage: 0.6 }] },
    options: { indexAxis: "y",  plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (it) => `${it.raw} records` } } },
      scales: { x: { grid: { color: css("--line") } }, y: { grid: { display: false } } } },
    plugins: [{ id: "labels", afterDatasetsDraw(chart) {
      const { ctx } = chart; ctx.save(); ctx.fillStyle = css("--muted"); ctx.font = "600 13px Barlow, sans-serif";
      chart.getDatasetMeta(0).data.forEach((bar, i) => ctx.fillText(counts[i], bar.x + 6, bar.y + 4)); ctx.restore(); } }],
  });

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

  renderOverviewMap();
}
const min = (k) => Math.min(...S.wards.map((w) => w[k]));
const max = (k) => Math.max(...S.wards.map((w) => w[k]));

function baseMap(id) {
  const m = L.map(id, { scrollWheelZoom: false, zoomSnap: 0.25 });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18, opacity: 0.55,
  }).addTo(m);
  S.maps[id] = m;
  return m;
}

function seqColor(v, lo, hi) {
  const t = Math.min(0.999, Math.max(0, (v - lo) / (hi - lo)));
  return SEQ[Math.floor(t * SEQ.length)];
}

function wardLayer(map, styleFn, tooltipFn) {
  const layer = L.geoJSON(S.geo, {
    style: (f) => ({ color: "#18191b", weight: 1.4, fillOpacity: 0.82, ...styleFn(S.byWard[f.properties.ward_id]) }),
    onEachFeature: (f, l) => {
      const w = S.byWard[f.properties.ward_id];
      l.bindTooltip(tooltipFn(w), { sticky: true });
      l.on({ click: () => openWard(w.ward_id), mouseover: () => { l.setStyle({ weight: 3, color: "#ff4a1f" }); l.bringToFront(); },
        mouseout: () => layer.resetStyle(l) });
    },
  }).addTo(map);
  layer.eachLayer((l) => {
    const c = l.getBounds().getCenter();
    L.tooltip({ permanent: true, direction: "center", className: "ward-label", interactive: false })
      .setContent(l.feature.properties.ward_id).setLatLng(polyLabelPoint(l) || c).addTo(map);
  });
  map._wardBounds = layer.getBounds();
  map.fitBounds(map._wardBounds, { padding: [8, 8] });
  return layer;
}

// Use the vertex-average of the largest ring as a label point; good enough for these ward shapes.
function polyLabelPoint(l) {
  try {
    let rings = l.getLatLngs();
    while (Array.isArray(rings[0]) && Array.isArray(rings[0][0])) rings = rings[0];
    const ring = Array.isArray(rings[0]) ? rings[0] : rings;
    const b = L.latLngBounds(ring).getCenter();
    return l.getBounds().contains(b) ? b : null;
  } catch { return null; }
}

function renderOverviewMap() {
  const m = baseMap("map-overview");
  const lo = min("facilities_per_100k"), hi = max("facilities_per_100k");
  wardLayer(m, (w) => ({ fillColor: seqColor(w.facilities_per_100k, lo, hi) }),
    (w) => `<b>${wardTitle(w.ward_id)}</b><br>${fmt(w.facilities_per_100k)} sites per 100k<br>${w.total_distinct_public_facilities} sites · pop ${fmt0(w.population_2011)}`);

  const groups = {};
  CATS.forEach((c, i) => {
    groups[c] = L.layerGroup(S.facilities.filter((f) => f.category === c && f.latitude && f.longitude).map((f) =>
      L.circleMarker([f.latitude, f.longitude], { radius: i < 2 ? 3.5 : 6, color: "#18191b", weight: 1,
        fillColor: CAT_COLOR[c], fillOpacity: 0.95 })
        .bindTooltip(`<b>${esc(f.facility_name)}</b><br>${CAT_LABEL[c]} · ward ${f.ward_id}${f.coordinates_approximate ? "<br><i>approximate location</i>" : ""}`)))
      .addTo(m);
  });
  document.getElementById("map-toggles").innerHTML = CATS.map((c) =>
    `<label class="toggle"><input type="checkbox" data-cat="${c}" checked><span class="dot" style="background:${CAT_COLOR[c]}"></span>${CAT_LABEL[c]}</label>`).join("");
  document.querySelectorAll("#map-toggles input").forEach((cb) => cb.addEventListener("change", () => {
    cb.checked ? groups[cb.dataset.cat].addTo(m) : m.removeLayer(groups[cb.dataset.cat]);
  }));

  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const d = L.DomUtil.create("div", "legend");
    const step = (hi - lo) / SEQ.length;
    d.innerHTML = "<b>Sites per 100k</b><br>" + SEQ.map((c, i) => `<i style="background:${c}"></i>${fmt(lo + i * step)} – ${fmt(lo + (i + 1) * step)}`).join("<br>");
    return d;
  };
  legend.addTo(m);
}

/* ---------------- Page 2 ---------------- */
function setupWardFilters() {
  const sel = document.getElementById("f-cluster");
  sel.innerHTML += S.clusters.map((c) => `<option value="${c.cluster_label}">Cluster ${c.cluster_label} (${c.n_wards} wards)</option>`).join("");
  ["f-category", "f-cluster"].forEach((id) => document.getElementById(id).addEventListener("change", renderWards));
}

function wardRowsForFilter() {
  const cat = document.getElementById("f-category").value;
  const cl = document.getElementById("f-cluster").value;
  const rows = S.wards.filter((w) => cl === "all" || String(w.cluster_label) === cl).map((w) => {
    const count = cat === "all" ? w.total_distinct_public_facilities : w[`${cat}_count`];
    return { ...w, sel_count: count, sel_rate: count / w.population_2011 * 1e5,
      sel_pps: count > 0 ? w.population_2011 / count : null };
  });
  // Shares are always relative to the whole city, so a cluster filter does not rescale them.
  const totPop = sum(S.wards, "population_2011");
  const totCount = cat === "all" ? sum(S.wards, "total_distinct_public_facilities") : sum(S.wards, `${cat}_count`);
  rows.forEach((r) => {
    const w = S.byWard[r.ward_id];
    const c = cat === "all" ? w.total_distinct_public_facilities : w[`${cat}_count`];
    r.sel_gap = w.population_2011 / totPop * 100 - c / totCount * 100;
  });
  const cityRate = totCount / totPop * 1e5;
  return { rows, cat, cl, cityRate };
}

function renderWards() {
  document.getElementById("scatter-key").innerHTML = S.clusters.map((c) =>
    `<span class="dot" style="background:${CLUSTER_COLOR[c.cluster_label]}"></span> ${c.cluster_label}`).join(" &nbsp;");
  const { rows, cat, cl, cityRate } = wardRowsForFilter();
  const what = cat === "all" ? "Sites" : `${CAT_LABEL[cat]} records`;
  document.getElementById("t-rate").textContent = `${what} per 100,000 residents`;
  document.getElementById("filter-note").textContent =
    `${rows.length} ward${rows.length === 1 ? "" : "s"} shown${cl !== "all" ? ` (cluster ${cl})` : ""}. Population and facility shares stay relative to all 24 wards.`;

  hbar("chart-rate", [...rows].sort((a, b) => b.sel_rate - a.sel_rate), "sel_rate",
    { color: SERIES[0], label: `${what} per 100k`, ref: { value: cityRate, label: `city-wide ${fmt(cityRate)}` }, onClick: openWard });
  hbar("chart-gap", [...rows].sort((a, b) => b.sel_gap - a.sel_gap), "sel_gap",
    { label: "Share gap (pp)", fmtV: (v) => `${v > 0 ? "+" : ""}${fmt(v)} pp`, colorFn: (r) => (r.sel_gap > 0 ? css("--red") : css("--blue")), onClick: openWard });
  const pps = [...rows].sort((a, b) => (b.sel_pps ?? -1) - (a.sel_pps ?? -1));
  hbar("chart-pps", pps, "sel_pps", { color: SERIES[0], label: "Residents per site", fmtV: (v) => (v == null ? "undefined (no sites)" : fmt0(v)), onClick: openWard,
    ref: { value: 1e5 / cityRate, label: "city-wide" } });

  makeChart("chart-scatter", {
    type: "scatter",
    data: { datasets: [{ data: rows.map((r) => ({ x: r.population_2011 / 1e5, y: r.sel_count, id: r.ward_id })),
      backgroundColor: rows.map((r) => CLUSTER_COLOR[r.cluster_label]), borderColor: css("--surface"), borderWidth: 1.5, pointRadius: 7, pointHoverRadius: 9 }] },
    options: {
      
      plugins: { legend: { display: false }, refLine: { value: 0, slope: cityRate / 1 },
        tooltip: { callbacks: { title: (it) => wardTitle(it[0].raw.id), label: (it) => [`Population ${fmt0(it.raw.x * 1e5)}`, `${what}: ${it.raw.y}`, `Cluster ${S.byWard[it.raw.id].cluster_label}`] } } },
      scales: { x: { title: { display: true, text: "Population, Census 2011 (lakh)" }, min: 0 },
        y: { title: { display: true, text: what }, min: 0 } },
      onClick: (_e, els) => { if (els.length) openWard(rows[els[0].index].ward_id); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
    },
    plugins: [{ id: "pointLabels", afterDatasetsDraw(chart) {
      const { ctx } = chart; ctx.save(); ctx.fillStyle = css("--muted"); ctx.font = "600 12px Barlow, sans-serif";
      chart.getDatasetMeta(0).data.forEach((p, i) => ctx.fillText(rows[i].ward_id, p.x + 8, p.y - 6)); ctx.restore(); } }],
  });

  renderTable("ward-table", rows, [
    ["ward_id", "Ward", (v) => v, "left"],
    ["population_2011", "Population 2011", fmt0],
    ["sel_count", cat === "all" ? "Sites" : "Records", fmt0],
    ["sel_rate", "Per 100k", fmt],
    ["sel_pps", "Residents / site", (v) => (v == null ? "–" : fmt0(v))],
    ["sel_gap", "Share gap (pp)", (v) => `${v > 0 ? "+" : ""}${fmt(v)}`],
    ["dispensary_count", "Disp.", fmt0], ["uphc_count", "UPHC", fmt0], ["public_hospital_count", "Hosp.", fmt0], ["maternity_hospital_count", "Mat.", fmt0],
    ["cluster_label", "Cluster", (v) => clusterPill(v)],
  ], "sel_rate", "asc");
}

function clusterPill(c) { return `<span class="pill" style="background:${CLUSTER_COLOR[c]}">${c}</span>`; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }

function renderTable(id, rows, cols, sortKey, dir) {
  const table = document.getElementById(id);
  const draw = (key, d) => {
    const sorted = [...rows].sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * (d === "asc" ? 1 : -1);
    });
    table.innerHTML = `<thead><tr>${cols.map(([k, l, , cls]) => `<th data-key="${k}" class="${cls || ""}" ${k === key ? `data-dir="${d}"` : ""}>${l}</th>`).join("")}</tr></thead>` +
      `<tbody>${sorted.map((r) => `<tr data-ward="${esc(r.ward_id)}">${cols.map(([k, , f, cls]) => `<td class="${cls || ""}">${f(r[k])}</td>`).join("")}</tr>`).join("")}</tbody>`;
    table.querySelectorAll("th").forEach((th) => th.addEventListener("click", () =>
      draw(th.dataset.key, th.dataset.key === key && d === "asc" ? "desc" : "asc")));
    table.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => openWard(tr.dataset.ward)));
  };
  draw(sortKey, dir);
}

/* ---------------- Page 3 ---------------- */
function renderClusters() {
  document.getElementById("cluster-cards").innerHTML = S.clusters.map((c) => `
    <div class="ccard" style="--c:${CLUSTER_COLOR[c.cluster_label]}">
      <h3>Cluster ${c.cluster_label} · ${c.n_wards} wards</h3>
      <div class="desc">${esc(c.cluster_name)}</div>
      <div class="wards">${esc(c.wards)}</div>
      <div class="meta">${fmt(c.facilities_per_100k_mean)} sites/100k (mean) · silhouette ${fmt(c.mean_silhouette, 2)}</div>
    </div>`).join("");

  const m = baseMap("map-clusters");
  wardLayer(m, (w) => ({ fillColor: CLUSTER_COLOR[w.cluster_label] }),
    (w) => `<b>${wardTitle(w.ward_id)}</b><br>Cluster ${w.cluster_label}: ${esc(w.cluster_name)}<br>silhouette ${fmt(w.silhouette_sample, 2)}`);
  const legend = L.control({ position: "topright" });
  legend.onAdd = () => {
    const d = L.DomUtil.create("div", "legend");
    d.innerHTML = "<b>Cluster</b><br>" + S.clusters.map((c) => `<i style="background:${CLUSTER_COLOR[c.cluster_label]}"></i>${c.cluster_label} · ${c.n_wards} wards`).join("<br>");
    return d;
  };
  legend.addTo(m);

  // Profiles: cluster mean of each feature as SD from the 24-ward mean (same as the static figure).
  const feats = CATS.map((c) => `${c}_per_100k`);
  const stats = Object.fromEntries(feats.map((f) => {
    const v = S.wards.map((w) => w[f]); const mu = v.reduce((a, b) => a + b, 0) / v.length;
    const sd = Math.sqrt(v.reduce((a, b) => a + (b - mu) ** 2, 0) / (v.length - 1));
    return [f, { mu, sd }];
  }));
  makeChart("chart-profile", {
    type: "bar",
    data: { labels: ["Dispensaries / 100k", "UPHCs / 100k", "Hospitals / 100k", "Maternity homes / 100k"],
      datasets: S.clusters.map((c) => ({ label: `Cluster ${c.cluster_label}`, backgroundColor: CLUSTER_COLOR[c.cluster_label], borderRadius: 3,
        data: feats.map((f) => (c[`${f}_mean`] - stats[f].mu) / stats[f].sd), raw: feats.map((f) => c[`${f}_mean`]) })) },
    options: { 
      plugins: { legend: { position: "bottom" },
        tooltip: { callbacks: { label: (it) => `${it.dataset.label}: mean ${fmt(it.dataset.raw[it.dataIndex])} per 100k (${it.raw > 0 ? "+" : ""}${fmt(it.raw)} SD)` } } },
      scales: { y: { title: { display: true, text: "SD from ward mean" } }, x: { grid: { display: false } } } },
  });

  const ks = S.kEval.map((r) => `K=${r.k}`);
  const final = S.kEval.findIndex((r) => String(r.final_choice).toLowerCase() === "true");
  const ptColor = S.kEval.map((_r, i) => (i === final ? css("--red") : SERIES[0]));
  makeChart("chart-inertia", {
    type: "line",
    data: { labels: ks, datasets: [{ label: "Inertia", data: S.kEval.map((r) => r.inertia), borderColor: SERIES[0], borderWidth: 2,
      pointBackgroundColor: ptColor, pointRadius: 6 }] },
    options: {  plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: "Within-cluster SS" } } } },
  });
  makeChart("chart-silhouette", {
    type: "line",
    data: { labels: ks, datasets: [
      { label: "Mean silhouette", data: S.kEval.map((r) => r.silhouette), borderColor: SERIES[0], borderWidth: 2, pointBackgroundColor: ptColor, pointRadius: 6 },
      { label: "Subsample stability (mean ARI)", data: S.kEval.map((r) => r.subsample80_ari_mean), borderColor: SERIES[1], borderWidth: 2, pointRadius: 5, pointStyle: "rect", borderDash: [5, 4] },
    ] },
    options: {  plugins: { legend: { position: "bottom" },
      tooltip: { callbacks: { afterBody: (it) => `Cluster sizes: ${S.kEval[it[0].dataIndex].cluster_sizes}${it[0].dataIndex === final ? "  (chosen)" : ""}` } } },
      scales: { y: { min: 0, max: 1 } } },
  });

  renderTable("cluster-table", S.wards, [
    ["ward_id", "Ward", (v) => v, "left"],
    ["cluster_label", "Cluster", (v) => clusterPill(v)],
    ["cluster_name", "Profile", (v) => esc(v), "left"],
    ["silhouette_sample", "Silhouette", (v) => fmt(v)],
    ["dispensary_per_100k", "Disp./100k", fmt], ["uphc_per_100k", "UPHC/100k", fmt],
    ["public_hospital_per_100k", "Hosp./100k", fmt], ["maternity_hospital_per_100k", "Mat./100k", fmt],
    ["cluster_k2_label", "K=2 label", fmt0],
  ], "cluster_label", "asc");
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
    </tbody></table>`;
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
