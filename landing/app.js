/* Landing page: the live ward sentence, section entrances, counters and the dashboard switcher. */
"use strict";

const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (s) => document.querySelector(s);

/* ---------- signature move: masked headline (after fonts so lines don't jump) ---------- */
(document.fonts ? document.fonts.ready : Promise.resolve()).then(() =>
  requestAnimationFrame(() => document.documentElement.classList.add("ready")));
setTimeout(() => document.documentElement.classList.add("ready"), 1500); // never leave the hero hidden

/* ---------- section entrances + counters ---------- */
document.querySelectorAll("[data-reveal]").forEach((el) => {
  const siblings = [...el.parentElement.querySelectorAll(":scope > [data-reveal], :scope > * > [data-reveal]")];
  el.style.setProperty("--d", Math.max(0, siblings.indexOf(el)));
});
const io = new IntersectionObserver((entries) => entries.forEach((e) => {
  if (!e.isIntersecting) return;
  e.target.classList.add("in");
  e.target.querySelectorAll("[data-count]").forEach(countUp);
  io.unobserve(e.target);
}), { threshold: 0.18, rootMargin: "0px 0px -6% 0px" });
document.querySelectorAll("[data-reveal]").forEach((el) => io.observe(el));

function countUp(el) {
  const target = Number(el.dataset.count);
  const decEl = el.parentElement.querySelector("[data-count-dec]");
  if (reduce || !Number.isFinite(target)) return;
  const t0 = performance.now(), dur = 1300;
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
    el.textContent = Math.round(target * e);
    if (decEl) decEl.textContent = "." + String(Math.round(Number(decEl.dataset.countDec) * e)).padStart(2, "0");
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ---------- moving picture: the dashboard drifts against the type as you scroll ---------- */
const obj = $(".object");
if (obj && !reduce) {
  let ticking = false;
  addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const r = obj.getBoundingClientRect(), mid = (r.top + r.height / 2 - innerHeight / 2) / innerHeight;
      if (Math.abs(mid) < 1.5 && !obj.matches(":hover")) obj.style.transform = `translateY(${(mid * -40).toFixed(1)}px) rotate(${(-4 + mid * 2).toFixed(2)}deg)`;
      ticking = false;
    });
  }, { passive: true });
  obj.addEventListener("mouseenter", () => { obj.style.transform = ""; });
}

/* ---------- showcase tabs swap the dashboard screenshot ---------- */
const shots = {
  predictor: "Heart risk predictor: a patient chart beside a bedside monitor with a live ECG, and the three model results",
  "overview-2": "Dashboard overview: test-set accuracy of the three models, the facility figures and the ward lookup",
  overview: "Earlier web version of the overview: facility counts by category and a ward map shaded by sites per 100,000 residents" };
const shotLink = { predictor: "dashboard/#predict", "overview-2": "dashboard/#overview", overview: "dashboard/#powerbi" };
document.querySelectorAll(".facts-tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".facts-tabs button").forEach((x) => x.setAttribute("aria-selected", x === b));
  const img = $("#show-img"), key = b.dataset.shot;
  img.classList.add("swap");
  setTimeout(() => {
    img.src = `landing/assets/dashboard-${key}.png`;
    img.alt = shots[key];
    obj.href = shotLink[key];
    img.onload = () => img.classList.remove("swap");
  }, reduce ? 0 : 220);
}));

/* ---------- the live sentence: pick a ward, the headline rewrites itself ---------- */
const W = { wards: [], byId: {}, paths: {}, city: null, lowest: null };

function parseCsv(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (c !== "\r") cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows;
  return body.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

function indian(n) {
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} crore`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} lakh`;
  return Math.round(n).toLocaleString("en-IN");
}

function drawMap(geo) {
  // Equirectangular projection scaled by cos(latitude), fitted into the 100 x 100 viewBox.
  const pts = [];
  const rings = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);
  geo.features.forEach((f) => rings(f.geometry).forEach((poly) => poly.forEach((ring) => ring.forEach((p) => pts.push(p)))));
  const k = Math.cos((19.07 * Math.PI) / 180);
  const xs = pts.map((p) => p[0] * k), ys = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const s = 92 / Math.max(x1 - x0, y1 - y0), ox = (100 - (x1 - x0) * s) / 2, oy = (100 - (y1 - y0) * s) / 2;
  const svg = $("#h-map");
  svg.innerHTML = geo.features.map((f) => {
    const d = rings(f.geometry).map((poly) => poly.map((ring) => "M" + ring.map((p) =>
      `${(ox + (p[0] * k - x0) * s).toFixed(2)},${(oy + (y1 - p[1]) * s).toFixed(2)}`).join("L") + "Z").join("")).join("");
    return `<path data-ward="${f.properties.ward_id}" d="${d}"><title>${f.properties.ward_id}</title></path>`;
  }).join("");
  svg.querySelectorAll("path").forEach((p) => { W.paths[p.dataset.ward] = p; });
}

function setNumber(el, text) {
  if (el.textContent === text) return;
  if (reduce) { el.textContent = text; return; }
  el.classList.add("swap");
  setTimeout(() => { el.textContent = text; el.classList.remove("swap"); }, 180);
}

function show(id) {
  const w = id ? W.byId[id] : null;
  const sites = w ? Number(w.total_distinct_public_facilities) : W.city.sites;
  const pop = w ? Number(w.population_2011) : W.city.pop;
  const rate = w ? Number(w.facilities_per_100k) : W.city.rate;
  setNumber($("#h-sites"), String(sites));
  setNumber($("#h-pop"), indian(pop));
  $("#h-sites").nextSibling.textContent = sites === 1 ? " health site" : " health sites";
  $("#w-rate").textContent = rate.toFixed(2);
  const r = w ? rankOf(id) : 0;
  $("#w-rank").textContent = !w ? "city-wide" : r === 1 ? "lowest of 24" : `${ordinal(r)} lowest of 24`;
  $("#w-select").value = id || "";
  Object.entries(W.paths).forEach(([k, p]) => p.classList.toggle("on", !id || k === id));
  const sw = $("#w-switch");
  sw.setAttribute("aria-pressed", String(id === W.lowest));
  $("#hero-title").setAttribute("aria-label", `${sites} health sites for ${indian(pop)} people${w ? ` in ward ${id}` : " in Mumbai"}`);
}
const rankOf = (id) => [...W.wards].sort((a, b) => a.facilities_per_100k - b.facilities_per_100k).findIndex((w) => w.ward_id === id) + 1;
const ordinal = (n) => { const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };

function step(dir) {
  const ids = W.wards.map((w) => w.ward_id), cur = $("#w-select").value;
  const i = cur ? ids.indexOf(cur) : (dir > 0 ? -1 : ids.length);
  const n = i + dir;
  show(n < 0 || n >= ids.length ? "" : ids[n]);
}

Promise.all([
  fetch("powerbi/data/dim_ward.csv").then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); }),
  fetch("data/processed/ward_boundaries.geojson").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
]).then(([csv, geo]) => {
  W.wards = parseCsv(csv).map((w) => ({ ...w, facilities_per_100k: Number(w.facilities_per_100k) }))
    .sort((a, b) => Number(a.ward_order) - Number(b.ward_order));
  W.byId = Object.fromEntries(W.wards.map((w) => [w.ward_id, w]));
  const pop = W.wards.reduce((a, w) => a + Number(w.population_2011), 0);
  const sites = W.wards.reduce((a, w) => a + Number(w.total_distinct_public_facilities), 0);
  W.city = { pop, sites, rate: (sites / pop) * 1e5 };
  W.lowest = [...W.wards].sort((a, b) => a.facilities_per_100k - b.facilities_per_100k)[0].ward_id;
  $("#w-select").insertAdjacentHTML("beforeend", W.wards.map((w) => `<option value="${w.ward_id}">${w.ward_id}</option>`).join(""));
  drawMap(geo);
  show("");
  drawMonitor();
  $("#w-select").addEventListener("change", (e) => show(e.target.value));
  $("#w-prev").addEventListener("click", () => step(-1));
  $("#w-next").addEventListener("click", () => step(1));
  $("#w-switch").addEventListener("click", () => show($("#w-switch").getAttribute("aria-pressed") === "true" ? "" : W.lowest));
}).catch(() => {
  // Without the pipeline outputs the sentence keeps its city-wide figures; the controls are hidden.
  document.querySelectorAll(".chip").forEach((c) => { c.hidden = true; });
  $(".frame").hidden = true;
});

/* ---------- the ward monitor: one heartbeat per ward, spike height = sites per 100,000 ---------- */
const MON = { base: 210, cell: 50, top: 34, minH: 34 };

function beatPath(x0, h) {
  // P wave, QRS complex (R peak of height h) and T wave, drawn in one 50-unit cell.
  const b = MON.base;
  return `L${x0 + 6} ${b} Q${x0 + 10} ${b - 12} ${x0 + 14} ${b} L${x0 + 19} ${b} L${x0 + 21} ${b + 8} ` +
    `L${x0 + 25} ${b - h} L${x0 + 29} ${b + 18} L${x0 + 32} ${b} L${x0 + 37} ${b} ` +
    `Q${x0 + 41.5} ${b - 18} ${x0 + 46} ${b} L${x0 + 50} ${b}`;
}

function drawMonitor() {
  const svg = $("#mon-svg");
  if (!svg || !W.wards.length) return;
  const rates = W.wards.map((w) => w.facilities_per_100k);
  const lo = Math.min(...rates), hi = Math.max(...rates);
  const height = (v) => MON.minH + ((v - lo) / (hi - lo)) * (MON.base - MON.top - MON.minH);
  const low3 = new Set([...W.wards].sort((a, b) => a.facilities_per_100k - b.facilities_per_100k).slice(0, 3).map((w) => w.ward_id));
  const name = (w) => (w.ward_name && w.ward_name !== w.ward_id ? `${w.ward_id} (${w.ward_name})` : `Ward ${w.ward_id}`);

  let trace = `M0 ${MON.base}`;
  const beats = W.wards.map((w, i) => {
    const x0 = i * MON.cell, h = height(w.facilities_per_100k), seg = `M${x0} ${MON.base} ` + beatPath(x0, h).slice(0);
    trace += " " + beatPath(x0, h);
    return `<g class="beat${low3.has(w.ward_id) ? " low" : ""}" tabindex="0" role="button" data-ward="${w.ward_id}"
        aria-label="${name(w)}: ${w.facilities_per_100k.toFixed(2)} sites per lakh people, 1 site for every ${Math.round(Number(w.population_per_facility)).toLocaleString("en-IN")} people">
      <rect x="${x0}" y="0" width="${MON.cell}" height="300" fill="transparent"></rect>
      <path class="beat-line" d="${seg}"></path>
      <text class="beat-val" x="${x0 + 25}" y="${MON.base - h - 10}" text-anchor="middle">${w.facilities_per_100k.toFixed(2)}</text>
      <text class="beat-code" x="${x0 + 25}" y="268" text-anchor="middle">${w.ward_id}</text>
    </g>`;
  }).join("");
  svg.innerHTML = `<path id="mon-trace" class="trace" d="${trace}"></path>${beats}`;

  const k = $("#mon-k"), v = $("#mon-v"), x = $("#mon-x");
  const lowest = [...W.wards].sort((a, b) => a.facilities_per_100k - b.facilities_per_100k);
  const city = () => {
    k.textContent = "City average"; v.textContent = W.city.rate.toFixed(2);
    const ppl = (w) => Math.round(Number(w.population_per_facility)).toLocaleString("en-IN");
    x.textContent = `About 1 site for every ${Math.round(1e5 / W.city.rate).toLocaleString("en-IN")} people. Fewest: ` +
      `${lowest[0].ward_name || lowest[0].ward_id}, 1 per ${ppl(lowest[0])}. Most: ${lowest.at(-1).ward_name || lowest.at(-1).ward_id}, 1 per ${ppl(lowest.at(-1))}.`;
    svg.querySelectorAll(".beat.on").forEach((g) => g.classList.remove("on"));
  };
  const pick = (g) => {
    const w = W.byId[g.dataset.ward];
    svg.querySelectorAll(".beat.on").forEach((b) => b.classList.remove("on"));
    g.classList.add("on");
    k.textContent = name(w); v.textContent = w.facilities_per_100k.toFixed(2);
    x.textContent = `${w.total_distinct_public_facilities} sites for ${indian(Number(w.population_2011))} people: 1 for every ` +
      `${Math.round(Number(w.population_per_facility)).toLocaleString("en-IN")}. ${ordinal(rankOf(w.ward_id))} lowest of 24.`;
  };
  svg.querySelectorAll(".beat").forEach((g) => {
    g.addEventListener("mouseenter", () => pick(g));
    g.addEventListener("focus", () => pick(g));
    g.addEventListener("click", () => { location.href = `dashboard/#ward=${g.dataset.ward}`; });
    g.addEventListener("keydown", (e) => { if (e.key === "Enter") location.href = `dashboard/#ward=${g.dataset.ward}`; });
  });
  svg.addEventListener("mouseleave", city);
  svg.addEventListener("focusout", (e) => { if (!svg.contains(e.relatedTarget)) city(); });
  city();

  // Signature motion: the trace sweeps in like a monitor, then a bright dot keeps running along it.
  const path = $("#mon-trace");
  if (reduce) return;
  const len = path.getTotalLength();
  path.style.strokeDasharray = `${len}`;
  path.style.strokeDashoffset = `${len}`;
  const mio = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    mio.disconnect();
    const anim = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }], { duration: 3200, easing: "linear", fill: "forwards" });
    anim.onfinish = () => {
      path.style.strokeDasharray = "none";
      svg.insertAdjacentHTML("beforeend", `<circle class="head" r="5"><animateMotion dur="16s" repeatCount="indefinite" rotate="auto"><mpath href="#mon-trace"></mpath></animateMotion></circle>`);
    };
  }), { threshold: 0.35 });
  mio.observe($(".monitor"));
}

/* ---------- the model report: filled from the same static API the dashboard reads ---------- */
fetch("dashboard/static-api/overview.json").then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then((o) => {
  const ms = o.models, cols = ["accuracy", "roc_auc", "recall", "f1"], pctCols = new Set(["accuracy", "recall"]);
  const best = Object.fromEntries(cols.map((c) => [c, Math.max(...ms.map((m) => m[c]))]));
  const label = { logistic_regression: "Logistic regression", random_forest: "Random forest", ann: "Neural network (MLP)" };
  // Same rounding as the dashboard's formatter (toFixed would show 0.9655 as 96.5% instead of 96.6%).
  const f = (v, d) => v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const cell = (m, c) => `<td${m[c] === best[c] ? ' class="best"' : ""}>${pctCols.has(c) ? f(m[c] * 100, 1) + "%" : f(m[c], 3)}</td>`;
  $("#report-rows").innerHTML = ms.map((m) => `<tr><th scope="row">${label[m.key] || m.label}</th>${cols.map((c) => cell(m, c)).join("")}</tr>`).join("");
  $("#r-test").textContent = o.clinical.test;
  $("#r-records").textContent = Number(o.clinical.records).toLocaleString("en-IN");
  $("#r-base").textContent = `${(o.clinical.majority_baseline_accuracy * 100).toFixed(1)}%`;
  const right = [...ms].sort((a, b) => b.accuracy - a.accuracy)
    .map((m) => `the ${{ logistic_regression: "logistic regression", random_forest: "random forest", ann: "neural network" }[m.key] || m.label} ${Math.round(m.accuracy * o.clinical.test)}`);
  $("#report-plain").textContent = `In plain words: tested on ${o.clinical.test} new patients, ${right[0].replace(/ (\d+)$/, " got $1 right")}, ` +
    `${right.slice(1).join(" and ")}.`;
}).catch(() => { /* the static table in the page stays */ });

/* The API docs link only works with the Python server; on a static host (GitHub Pages) it would be a 404. */
if (location.hostname.endsWith("github.io")) {
  document.querySelectorAll('a[href="/api/docs"]').forEach((a) => { (a.closest("li") || a).hidden = true; });
}
