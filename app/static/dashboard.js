let iChart = null;
let mrChart = null;
let zoneChart = null;
let activeRegion = null;

const REGION_LABELS = {
  manhattan: "Manhattan (baseline)",
  queens: "Queens (high delay)",
  brooklyn: "Brooklyn (mixed)",
};

const CHART_PALETTE = {
  manhattan: { line: "#00d4aa", fill: "rgba(0, 212, 170, 0.25)", bar: "#34d399" },
  queens: { line: "#ff6b6b", fill: "rgba(255, 107, 107, 0.25)", bar: "#f87171" },
  brooklyn: { line: "#a78bfa", fill: "rgba(167, 139, 250, 0.3)", bar: "#c084fc" },
};

function setLoading(on) {
  document.getElementById("loading").classList.toggle("hidden", !on);
}

function setTheme(regionId) {
  document.body.classList.remove("theme-manhattan", "theme-queens", "theme-brooklyn");
  if (regionId) document.body.classList.add(`theme-${regionId}`);
}

function setActiveButton(regionId) {
  document.querySelectorAll(".region-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.region === regionId);
  });
}

function renderAnalysis(data) {
  const root = document.getElementById("resultsRoot");
  root.classList.remove("hidden");
  root.style.animation = "none";
  void root.offsetHeight;
  root.style.animation = "";

  const warnEl = document.getElementById("warnings");
  if (data.warnings && data.warnings.length) {
    warnEl.innerHTML =
      "<strong>Notes:</strong><ul>" + data.warnings.map((w) => `<li>${w}</li>`).join("") + "</ul>";
    warnEl.classList.remove("hidden");
  } else {
    warnEl.classList.add("hidden");
  }

  const sumEl = document.getElementById("summary");
  if (data.summary) {
    const s = data.summary;
    const items = [
      ["Mean (min)", s.mean],
      ["Median", s.median],
      ["Std dev", s.stdev],
      ["90th %ile", s.p90],
      ["95th %ile", s.p95],
      ["N", s.n],
    ];
    sumEl.innerHTML = items
      .map(
        ([label, val]) =>
          `<div class="card"><div class="label">${label}</div><div class="value">${Number(val).toFixed(2)}</div></div>`
      )
      .join("");
  }

  const alertsEl = document.getElementById("alerts");
  if (data.zone_alerts && data.zone_alerts.length) {
    alertsEl.innerHTML =
      "<h2>Zone alerts</h2>" +
      data.zone_alerts.map((a) => `<div class="alert-item">${a.message}</div>`).join("");
  } else {
    alertsEl.innerHTML = "<h2>Zone alerts</h2><p>No zones flagged under current rules.</p>";
  }

  const palette = CHART_PALETTE[activeRegion] || CHART_PALETTE.manhattan;

  if (data.limits_log && data.chart_points && data.chart_points.length) {
    renderIChart(data, palette);
    renderMrChart(data, palette);
  }

  if (data.zone_summaries && data.zone_summaries.length) {
    renderZoneChart(data.zone_summaries, palette);
  }
}

function renderIChart(data, palette) {
  const pts = data.chart_points;
  const lim = data.limits_log;
  const labels = pts.map((p) => p.call_received.slice(0, 16));
  const values = pts.map((p) => p.response_min);
  const colors = pts.map((p) => (p.individual_ooc ? "#ff4757" : palette.line));

  if (iChart) iChart.destroy();
  iChart = new Chart(document.getElementById("iChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Response (min)",
          data: values,
          pointBackgroundColor: colors,
          borderColor: palette.line,
          backgroundColor: palette.fill,
          fill: true,
          tension: 0.35,
        },
        {
          label: "UCL",
          data: pts.map(() => lim.ucl_min),
          borderColor: "#ff4757",
          borderDash: [6, 4],
          pointRadius: 0,
        },
        {
          label: "Center",
          data: pts.map(() => lim.center_min),
          borderColor: "#ffd93d",
          borderDash: [4, 4],
          pointRadius: 0,
        },
        {
          label: "LCL",
          data: pts.map(() => lim.lcl_min),
          borderColor: "#ff4757",
          borderDash: [6, 4],
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      animation: { duration: 700, easing: "easeOutQuart" },
      scales: {
        x: { ticks: { color: "#ccc" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { title: { display: true, text: "Minutes", color: "#ddd" }, ticks: { color: "#ccc" }, grid: { color: "rgba(255,255,255,0.08)" } },
      },
      plugins: { legend: { labels: { color: "#eee" } } },
    },
  });
}

function renderMrChart(data, palette) {
  const pts = data.chart_points.filter((p) => p.moving_range_log != null);
  const lim = data.limits_log;
  const labels = pts.map((p) => p.call_received.slice(0, 16));
  const values = pts.map((p) => p.moving_range_log);
  const colors = pts.map((p) => (p.mr_ooc ? "#ff4757" : palette.bar));

  if (mrChart) mrChart.destroy();
  mrChart = new Chart(document.getElementById("mrChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "MR (log)",
          data: values,
          pointBackgroundColor: colors,
          borderColor: palette.bar,
          tension: 0.3,
        },
        {
          label: "MR UCL",
          data: pts.map(() => lim.mr_ucl_log),
          borderColor: "#ff4757",
          borderDash: [6, 4],
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      animation: { duration: 700 },
      scales: {
        x: { ticks: { color: "#ccc" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#ccc" }, grid: { color: "rgba(255,255,255,0.08)" } },
      },
      plugins: { legend: { labels: { color: "#eee" } } },
    },
  });
}

function renderZoneChart(zones, palette) {
  const labels = zones.map((z) => z.zone);
  const p90 = zones.map((z) => z.p90);
  const target = zones.map(() => 8);
  const barColors = p90.map((v) => (v > 8 ? "#ff6b6b" : palette.bar));

  if (zoneChart) zoneChart.destroy();
  zoneChart = new Chart(document.getElementById("zoneChart"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "90th percentile (min)", data: p90, backgroundColor: barColors, borderRadius: 8 },
        { label: "8 min target", data: target, type: "line", borderColor: "#ffd93d", pointRadius: 0, borderWidth: 2 },
      ],
    },
    options: {
      responsive: true,
      animation: { duration: 650 },
      scales: {
        x: { ticks: { color: "#ccc" }, grid: { display: false } },
        y: { ticks: { color: "#ccc" }, grid: { color: "rgba(255,255,255,0.08)" } },
      },
      plugins: { legend: { labels: { color: "#eee" } } },
    },
  });
}

async function loadRegion(regionId) {
  if (activeRegion === regionId) return;
  activeRegion = regionId;
  setActiveButton(regionId);
  setTheme(regionId);
  const status = document.getElementById("regionStatus");
  status.textContent = `Loading ${REGION_LABELS[regionId] || regionId}…`;
  setLoading(true);

  try {
    const res = await fetch(`/api/analyze/${regionId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Could not load region data");
    }
    const data = await res.json();
    status.textContent = `Showing ${data.region_label || regionId} — ${data.n_incidents} incidents`;
    renderAnalysis(data);
  } catch (e) {
    status.textContent = `Error: ${e.message}`;
    alert(e.message);
  } finally {
    setLoading(false);
  }
}

document.querySelectorAll(".region-btn").forEach((btn) => {
  btn.addEventListener("click", () => loadRegion(btn.dataset.region));
});

loadRegion("manhattan");
