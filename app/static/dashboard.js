// Zone-first EMS dashboard. Every number comes from the API (app/qc.py); this file only displays it.
// URLs are relative ("api/...") so the page also works under Posit Connect's /content/{guid}/ path.

const STATUS = {
  normal: { icon: "🟢", label: "Normal" },
  watch: { icon: "🟡", label: "Watch" },
  needs_attention: { icon: "🔴", label: "Needs attention" },
  insufficient_data: { icon: "⚪", label: "Insufficient data" },
};
const STATUS_COLOR = { normal: "#34d399", watch: "#ffd93d", needs_attention: "#ff4757", insufficient_data: "#a5a3c4" };
const SCENARIO_LABELS = {
  no_delay: "No delay",
  stable_operations: "Stable operations",
  high_delay: "High delay",
};
// In-control points are never red, so red always means "above the control limit".
const CHART_PALETTE = {
  stable: { line: "#7dd3fc", bar: "#a5b4fc" },
  patterns: { line: "#7dd3fc", bar: "#a5b4fc" },
  minimal: { line: "#7dd3fc", bar: "#a5b4fc" },
  upload: { line: "#7dd3fc", bar: "#a5b4fc" },
};
const MAX_POINTS = 3000; // chart keeps every out-of-control call plus an even sample of the rest
const MIN_BOX_CALLS = 5; // must match app/qc.py BOX_MIN_CALLS

let period = "monthly";
let theme = null;
let openZone = null;
let iChart = null;
let mrChart = null;
let zoneChart = null;
let boxGroup = "weekday";

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? "–" : Number(v).toFixed(d));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const query = () => `period=${period}`;
const palette = () => CHART_PALETTE[theme] || CHART_PALETTE.stable;

function setLoading(on) {
  $("loading").classList.toggle("hidden", !on);
}

function setTheme(name) {
  theme = name;
  document.body.classList.remove("theme-stable", "theme-patterns", "theme-minimal", "theme-upload");
  if (name) document.body.classList.add(`theme-${name}`);
  document.querySelectorAll(".region-btn").forEach((b) => b.classList.toggle("active", b.dataset.theme === name));
}

async function api(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  return body;
}

function badge(status) {
  const s = STATUS[status];
  return `<span class="badge ${status}">${s.icon} ${s.label}</span>`;
}

const DARK_SCALES = {
  x: { ticks: { color: "#ccc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
  y: { ticks: { color: "#ccc" }, grid: { color: "rgba(255,255,255,0.08)" } },
};
const LEGEND = { labels: { color: "#eee" } };

// ---- overview -----------------------------------------------------------------------------
function conditionLine(z) {
  if (!z.conditions) return "";
  if (!z.conditions.available) return "Operational factors unavailable in this data";
  return z.conditions.conditions
    .map((c) => `${c.name}: ${c.flagged ? `<span class="flag">${c.level}</span>` : "Normal"}`)
    .join(" · ");
}

function renderOverview(data) {
  const root = $("resultsRoot");
  root.classList.remove("hidden");

  const warn = $("warnings");
  if (data.warnings.length) {
    warn.innerHTML = "<strong>Data notes:</strong><ul>" + data.warnings.map((w) => `<li>${esc(w)}</li>`).join("") + "</ul>";
    warn.classList.remove("hidden");
  } else warn.classList.add("hidden");

  const name = SCENARIO_LABELS[data.dataset] || data.dataset;
  $("regionStatus").textContent = `Showing ${name} — ${data.n_incidents.toLocaleString("en-US")} incidents, ` +
    `${data.data_start?.slice(0, 10)} to ${data.data_end?.slice(0, 10)} · ${period} view (ending at the latest call).`;

  $("zones").innerHTML = data.zones.map((z) => `
    <button type="button" class="zone-card ${z.status}${z.zone === openZone ? " open" : ""}" data-zone="${esc(z.zone)}">
      <h3>${esc(z.zone)}</h3>
      ${badge(z.status)}
      <div class="p90">${z.metrics ? `P90 ${fmt(z.metrics.p90)} min` : "–"}</div>
      ${z.normal ? `<p class="reason">Normal p90 ${fmt(z.normal.p90)} min${z.normal.source.startsWith("NYC") ? " (NYC)" : " (own first 14 days)"}</p>` : ""}
      <p class="reason">${esc(z.reasons[0])}</p>
      ${z.pattern ? `<p class="patt">${esc(z.pattern)}</p>` : ""}
      ${z.status === "normal" ? "" : `<p class="conds">${conditionLine(z)}</p>`}
    </button>`).join("");
  document.querySelectorAll(".zone-card").forEach((el) => el.addEventListener("click", () => openDetail(el.dataset.zone)));

  renderZoneChart(data);
  if (openZone && data.zones.some((z) => z.zone === openZone)) openDetail(openZone);
  else closeDetail();
}

function renderZoneChart(data) {
  const zones = data.zones.filter((z) => z.metrics);
  if (zoneChart) zoneChart.destroy();
  zoneChart = new Chart($("zoneChart"), {
    type: "bar",
    data: {
      labels: zones.map((z) => z.zone),
      datasets: [
        { label: "90th percentile (min)", data: zones.map((z) => z.metrics.p90),
          backgroundColor: zones.map((z) => STATUS_COLOR[z.status]), borderRadius: 8 },
        { label: "Normal p90 (NYC, 12 months)", data: zones.map((z) => z.normal?.p90 ?? null),
          backgroundColor: "rgba(255,255,255,0.35)", borderRadius: 8 },
      ],
    },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 650 },
      scales: { ...DARK_SCALES, x: { ...DARK_SCALES.x, grid: { display: false } } }, plugins: { legend: LEGEND } },
  });
}

// ---- zone detail --------------------------------------------------------------------------
function renderDetailCards(d) {
  const s = d.summary || {};
  const items = [["Calls", s.n, 0], ["Median", s.median, 1], ["Mean", s.mean, 1], ["Std dev", s.stdev, 1],
    ["p90", s.p90, 1], ["p95", s.p95, 1]];
  $("detailCards").innerHTML = items.map(([label, v, dec]) =>
    `<div class="card"><div class="label">${label}${dec ? " (min)" : ""}</div><div class="value">${fmt(v, dec)}</div></div>`).join("");
}

function renderStats(d) {
  const s = d.summary || {}, b = d.normal || {};
  const rows = [["", "This period", b.source?.startsWith("NYC") ? "Normal (NYC, 12 months)" : "Normal (first 14 days)"]];
  for (const [label, key, dec] of [["Calls", "n", 0], ["Median (min)", "median", 1], ["p90 (min)", "p90", 1], ["p95 (min)", "p95", 1]])
    rows.push([label, fmt(s[key], dec), fmt(b[key], dec)]);
  if (d.limits) {
    rows.push(["Centerline (min)", "", fmt(d.limits.center_min, 2)]);
    rows.push(["Upper control limit (min)", "", fmt(d.limits.ucl_min, 2)]);
    rows.push(["Lower control limit (min)", "", fmt(d.limits.lcl_min, 2)]);
  }
  if (d.metrics) {
    rows.push(["Calls above UCL", `${d.metrics.n_above_ucl}`, `${fmt(d.metrics.expected_above_ucl)} expected by chance`]);
    if (d.metrics.p90_ci95) rows.push(["p90 95% bootstrap interval", `${fmt(d.metrics.p90_ci95[0])}–${fmt(d.metrics.p90_ci95[1])}`, `normal ${fmt(b.p90)}`]);
    if (d.metrics.p90_ci99) rows.push(["p90 99% bootstrap interval", `${fmt(d.metrics.p90_ci99[0])}–${fmt(d.metrics.p90_ci99[1])}`, ""]);
  }
  $("detailStats").innerHTML = rows.map((r, i) => `<tr>${r.map((c) => (i === 0 ? `<th>${c}</th>` : `<td>${c}</td>`)).join("")}</tr>`).join("");
}

function renderConditions(d) {
  const c = d.conditions;
  if (!c || !c.available) {
    $("detailConditions").innerHTML = "<tr><td>Operational contributing factors are unavailable in the uploaded data.</td></tr>";
  } else {
    const show = (name, v) => (name === "Traffic" ? `${fmt(v * 100, 0)}% High` : fmt(v, 1));
    $("detailConditions").innerHTML = "<tr><th>Condition</th><th>Now</th><th>Baseline</th><th></th></tr>" +
      c.conditions.map((x) => `<tr><td>${x.name}<br><small>${x.unit}</small></td><td>${show(x.name, x.current)}</td>
        <td>${show(x.name, x.baseline)}</td><td class="${x.flagged ? "flag" : ""}">${x.flagged ? "🔺 " + x.level : "Normal"}</td></tr>`).join("") +
      (c.time_of_day ? `<tr><td colspan="4">Most long responses: <strong>${c.time_of_day}</strong></td></tr>` : "");
  }
  $("detailPattern").textContent = d.pattern ? `Pattern: ${d.pattern}` : "";
}

function samplePoints(points) {
  if (points.length <= MAX_POINTS) return points;
  const step = Math.ceil(points.length / MAX_POINTS);
  return points.filter((p, i) => p.above_ucl || p.below_lcl || p.mr_above_ucl || i % step === 0);
}

function renderCharts(d) {
  if (iChart) iChart.destroy();
  if (mrChart) mrChart.destroy();
  if (!d.points || !d.limits) return;
  const pts = samplePoints(d.points);
  const pal = palette();
  $("iChartNote").textContent = "Red points = calls above the upper control limit (special cause). Dashed lines = limits from the baseline." +
    (pts.length < d.points.length ? ` Showing ${pts.length.toLocaleString("en-US")} of ${d.points.length.toLocaleString("en-US")} calls (all out-of-control calls kept).` : "");
  const labels = pts.map((p) => p.dispatch_time.slice(5, 16));
  const limit = (label, value, color) => ({ label, data: pts.map(() => value), borderColor: color, borderDash: [6, 4],
    borderWidth: 2, pointRadius: 0, pointHitRadius: 0 });
  iChart = new Chart($("iChart"), {
    type: "line",
    data: { labels, datasets: [
      { label: "Response (min)", data: pts.map((p) => p.response_time_min), showLine: false,
        pointRadius: pts.map((p) => (p.above_ucl ? 4 : 2)),
        pointBackgroundColor: pts.map((p) => (p.above_ucl ? "#ff4757" : pal.line)), borderColor: pal.line },
      limit("UCL", d.limits.ucl_min, "#ff4757"),
      limit("Center", d.limits.center_min, "#ffd93d"),
      limit("LCL", d.limits.lcl_min, "#ff4757"),
    ] },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 700, easing: "easeOutQuart" },
      interaction: { mode: "nearest", intersect: false },
      scales: { ...DARK_SCALES, y: { ...DARK_SCALES.y, title: { display: true, text: "Minutes", color: "#ddd" } } },
      plugins: { legend: LEGEND, tooltip: { callbacks: {
        title: (items) => `${pts[items[0].dataIndex].incident_id} · ${pts[items[0].dataIndex].dispatch_time}`,
        label: (item) => `${item.dataset.label}: ${fmt(item.parsed.y, 2)} min` } } } },
  });
  const mpts = pts.filter((p) => p.moving_range_log != null);
  mrChart = new Chart($("mrChart"), {
    type: "line",
    data: { labels: mpts.map((p) => p.dispatch_time.slice(5, 16)), datasets: [
      { label: "MR (log)", data: mpts.map((p) => p.moving_range_log), showLine: false, pointRadius: 2,
        pointBackgroundColor: mpts.map((p) => (p.mr_above_ucl ? "#ff4757" : pal.bar)), borderColor: pal.bar },
      { label: "MR UCL", data: mpts.map(() => d.limits.mr_ucl_log), borderColor: "#ff4757", borderDash: [6, 4],
        borderWidth: 2, pointRadius: 0, pointHitRadius: 0 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 700 }, scales: DARK_SCALES,
      plugins: { legend: LEGEND } },
  });
}

// ---- the two descriptive charts (H-09) ------------------------------------------------------
// Every number below arrives from the API (app/qc.py). This file computes no quartile, no
// percentile and no control limit — it only positions what it is given, and neither chart can
// change a zone's status.
async function loadDescriptiveCharts(zone) {
  $("boxPlot").innerHTML = `<p class="empty-note">loading…</p>`;
  $("heatGrid").innerHTML = `<p class="empty-note">loading…</p>`;
  try {
    const [box, heat] = await Promise.all([
      api(`api/charts/boxplot/${encodeURIComponent(zone)}?${query()}&group=${boxGroup}`),
      api(`api/charts/heatmap/${encodeURIComponent(zone)}?${query()}`),
    ]);
    if (openZone !== zone) return; // the user moved on to another zone
    renderBoxPlot(box);
    renderHeatmap(heat);
  } catch (err) {
    $("boxPlot").innerHTML = `<p class="empty-note">${esc(err.message)}</p>`;
  }
}

function renderBoxPlot(payload) {
  const host = $("boxPlot");
  const drawn = payload.groups.filter((g) => g.boxplot);
  if (!drawn.length) {
    host.innerHTML = `<p class="empty-note">No ${esc(payload.group)} in this period has the
      ${MIN_BOX_CALLS} calls a box plot needs, so there is nothing to compare — try a longer
      review period.</p>`;
    return;
  }
  let lo = Math.min(...drawn.map((g) => g.boxplot.whisker_low_min));
  let hi = Math.max(...drawn.map((g) => g.boxplot.whisker_high_min));
  drawn.forEach((g) => {
    const outs = g.boxplot.outlier_calls;
    if (outs.length) hi = Math.max(hi, outs[outs.length - 1]);
  });
  lo = Math.max(0.4, lo / 1.4);
  hi *= 1.2;
  const pos = (v) => 100 - ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * 100;
  const ticks = [1, 2, 5, 10, 20, 30, 60, 120, 300, 600].filter((t) => t >= lo && t <= hi);
  const axis = ticks.map((t) => `<span class="box-tick" style="top:${pos(t)}%">${t}</span>`).join("");

  const cols = payload.groups.map((g) => {
    const label = payload.group === "weekday" ? g.group.slice(0, 3) : g.group.slice(5);
    const b = g.boxplot;
    if (!b) {
      return `<div class="box-col"><span class="box-none" title="${esc(g.group)}: ${g.n} calls, fewer than ${MIN_BOX_CALLS}">${g.n}<small>calls</small></span><span class="box-name">${esc(label)}</span></div>`;
    }
    const shown = b.outlier_calls.slice(-8);
    const dots = shown.map((v) => `<span class="box-dot" style="top:${pos(v)}%" title="${fmt(v)} min — beyond the fence"></span>`).join("");
    const more = b.outlier_calls.length > shown.length
      ? `<span class="box-more" style="top:${pos(shown[0])}%" title="${b.outlier_calls.length - shown.length} more beyond the fence">+${b.outlier_calls.length - shown.length}</span>` : "";
    const top = pos(b.whisker_high_min);
    const bottom = pos(b.whisker_low_min);
    return `<div class="box-col" title="${esc(g.group)}: ${b.n} calls · median ${fmt(b.median_min)} min · middle half ${fmt(b.q1_min)}–${fmt(b.q3_min)} min · ${b.n_outliers} beyond the fence">
      <span class="box-whisker" style="top:${top}%;height:${Math.max(0.5, bottom - top)}%"></span>
      <span class="box-cap" style="top:${top}%"></span>
      <span class="box-cap" style="top:${bottom}%"></span>
      <span class="box-body" style="top:${pos(b.q3_min)}%;height:${Math.max(1, pos(b.q1_min) - pos(b.q3_min))}%"></span>
      <span class="box-median" style="top:${pos(b.median_min)}%"></span>
      ${dots}${more}
      <span class="box-name">${esc(label)}</span>
    </div>`;
  }).join("");

  host.innerHTML = `<div class="box-plot-inner">
      <div class="box-axis">${axis}</div>
      <div class="box-cols">${cols}</div>
    </div>
    <p class="box-foot">Minutes, log scale. A dot above the whisker is a call beyond
      Q3 + 1.5×IQR on ln(minutes).
      ${payload.comparable ? "" : `<strong>${esc(payload.note || "Only one group has enough calls — one box is not a comparison.")}</strong>`}</p>`;
}

function renderHeatmap(payload) {
  const host = $("heatGrid");
  const values = payload.cells.flat().map((c) => c.value).filter((v) => v !== null);
  const hi = values.length ? Math.max(...values) : 0;
  const lo = values.length ? Math.min(...values) : 0;
  const level = (v) => (hi === lo ? 0.5 : (v - lo) / (hi - lo));
  const ramp = (l) => `hsl(${Math.round(205 - 205 * l)}, 88%, ${Math.round(60 - 14 * l)}%)`;

  const head = `<div class="heat-row heat-head"><span class="heat-day"></span>`
    + payload.hours.map((h) => `<span class="heat-h">${h % 3 === 0 ? h : ""}</span>`).join("") + `</div>`;

  const rows = payload.cells.map((row, d) => `<div class="heat-row">
      <span class="heat-day">${esc(payload.weekday_labels[d].slice(0, 3))}</span>
      ${row.map((c, h) => {
        const when = `${payload.weekday_labels[d]} ${String(h).padStart(2, "0")}:00`;
        if (c.value === null) {
          return `<span class="heat-cell thin" title="${esc(when)} — ${c.n} calls, fewer than ${payload.minimum}: not enough calls">·</span>`;
        }
        const l = level(c.value);
        return `<span class="heat-cell" style="background:${ramp(l)}" title="${esc(when)} — ${payload.stat} ${fmt(c.value)} min from ${c.n} calls">${Math.round(c.value)}</span>`;
      }).join("")}
    </div>`).join("");

  host.innerHTML = head + rows
    + `<p class="heat-foot">Each cell: the <strong>${esc(payload.stat)}</strong> in minutes for
       ${esc(payload.zone)} · ${payload.n_total.toLocaleString()} calls in the period ·
       ${payload.n_cells_with_value} of 168 cells have ≥ ${payload.minimum} calls,
       ${payload.n_cells_empty} are grey. A shorter period leaves most cells grey: one zone's month
       is about 450 calls across 168 cells. Read this chart at Yearly.</p>`;
  if (payload.n_cells_with_value === 0) {
    host.insertAdjacentHTML("afterbegin",
      `<p class="empty-note"><strong>Every cell is grey.</strong> This zone has
        ${payload.n_total.toLocaleString()} calls in a ${esc(payload.period)} period, which is not
        enough for a p90 per weekday and hour. Switch the review period to <strong>Yearly</strong>
        to read this chart — or read the box plot above, which needs only ${MIN_BOX_CALLS} calls per
        group.</p>`);
  }
}

async function openDetail(zone) {
  openZone = zone;
  document.querySelectorAll(".zone-card").forEach((el) => el.classList.toggle("open", el.dataset.zone === zone));
  try {
    const d = await api(`api/zone/${encodeURIComponent(zone)}?${query()}`);
    $("detailTitle").textContent = `${d.zone} · ${period}`;
    $("detailStatus").innerHTML = badge(d.status) +
      (d.metrics?.shift_start_day ? ` &nbsp;Shift started around <strong>${d.metrics.shift_start_day}</strong>` : "");
    $("detailReasons").innerHTML = d.reasons.map((r) => `<li>${esc(r)}</li>`).join("");
    renderDetailCards(d);
    renderStats(d);
    renderConditions(d);
    $("detail").classList.remove("hidden");
    renderCharts(d);
    loadDescriptiveCharts(zone);
  } catch (err) {
    alert(err.message);
  }
}

function closeDetail() {
  openZone = null;
  $("detail").classList.add("hidden");
  document.querySelectorAll(".zone-card").forEach((el) => el.classList.remove("open"));
}

// ---- actions ------------------------------------------------------------------------------
async function run(promise) {
  setLoading(true);
  try {
    renderOverview(await promise);
  } catch (err) {
    $("regionStatus").textContent = `Error: ${err.message}`;
    alert(err.message);
  } finally {
    setLoading(false);
  }
}

document.querySelectorAll("[data-sample]").forEach((btn) => btn.addEventListener("click", () => {
  setTheme(btn.dataset.theme);
  closeDetail();
  $("regionStatus").textContent = `Loading ${SCENARIO_LABELS[btn.dataset.sample]}…`;
  run(api(`api/samples/${btn.dataset.sample}?${query()}`, { method: "POST" }));
}));

$("csvFile").addEventListener("change", (e) => {
  if (!e.target.files.length) return;
  const form = new FormData();
  form.append("file", e.target.files[0]);
  setTheme("upload");
  closeDetail();
  run(api(`api/upload?${query()}`, { method: "POST", body: form }));
  e.target.value = "";
});

document.querySelectorAll("[data-period]").forEach((el) => el.addEventListener("click", () => {
  period = el.dataset.period;
  document.querySelectorAll("[data-period]").forEach((b) => b.classList.toggle("active", b === el));
  if (theme) run(api(`api/overview?${query()}`));
  if (openZone) openDetail(openZone); // the detail, and both descriptive charts, are period-specific
}));

document.querySelectorAll("[data-boxgroup]").forEach((el) => el.addEventListener("click", () => {
  boxGroup = el.dataset.boxgroup;
  document.querySelectorAll("[data-boxgroup]").forEach((b) => b.classList.toggle("active", b === el));
  $("boxTitle").textContent = boxGroup === "weekday"
    ? "Median and spread by day of week" : "Median and spread by month";
  if (openZone) loadDescriptiveCharts(openZone);
}));

$("btnCloseDetail").addEventListener("click", closeDetail);

$("incidentForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = Object.fromEntries([...new FormData(e.target).entries()].filter(([, v]) => v !== ""));
  if (body.available_units) body.available_units = Number(body.available_units);
  await run(api(`api/incident?${query()}`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }));
  e.target.reset();
});

// start on the dataset that proves the tool does not cry wolf
document.querySelector('[data-sample="no_delay"]').click();
