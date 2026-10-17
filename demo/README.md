# Demo walkthrough — NYC EMS Response Time Dashboard

**Team:** Chiblings · **Prompt #2** (Health Systems Emergency Response)

**Live app (judges):**  
https://connect.systems-apps.com/content/1d6d6d65-03cd-48d8-b0ac-8a07b1f3e27a/

Open in a **logged-out / private** window. No login required if Connect access is set to Anyone.

**Repo:** https://github.com/alptlg/6s_hackathon

---

## Before you start

- Default view: **Full Year** (change with **Last 6 Mo**, **Last 1 Mo**, **Last Week**, **Last Day**).
- Click a **borough card** to open the borough page (I-MR, MR, Cpk, conditions).
- **Good / Fair / Bad** on tiles compares response levels to display thresholds (< 8, 8–15, ≥ 15 min);
  **Cpk** is the formal capability index vs the **8-minute** NFPA 1710 upper spec (`app/qc.py`).

Verify statistics in the terminal (full CSV, all rows):

```bash
pip install -r app/requirements.txt
pytest tests
python app/cli.py --scenario delay --borough Queens --window all
```

---

## Scenario 1 — Stable Operations

**Load:** Open the live URL → click **Stable Operations**.

**Look at:** Home borough cards — geometric mean and 90th percentile for each borough; citywide
condition bar charts (traffic, units, priority).

**Drill-down:** Click **Queens** → summary tiles (geo mean, p90, **Cpk (USL=8)**), I-chart on
ln(response time), MR chart, **OOC** count in the chart header.

**Spot-check (CLI, full year, all boroughs):** geo mean ≈ **11.12** min, p90 ≈ **23.23** min,
Cpk ≈ **−0.18** (`python app/cli.py --scenario stable`).

**How to read this:** Typical operations still miss the 8-minute capability target on average (negative
Cpk), but the process looks **stable** on the I-MR chart relative to its own Phase I limits.

---

## Scenario 2 — High Delay

**Load:** Click **High Delay**.

**Look at:** Borough cards shift upward — geo means and p90s rise; more **Bad** badges on tiles.

**Drill-down:** **Queens** → note **Cpk** well below 1.0, higher **OOC** rate, condition charts
show which traffic/priority buckets coincide with out-of-control points.

**Spot-check (CLI):** citywide geo mean ≈ **19.58** min, p90 ≈ **48.40** min, Cpk ≈ **−0.43**.

**How to read this:** A sustained deterioration story — typical and tail response times move up, and
capability against 8 minutes is clearly **not capable**; use I-MR OOC points to discuss isolated
calls vs overall shift (conditions are **associated with**, not proven causes).

---

## Scenario 3 — No Delay / Fast

**Load:** Click **No Delay**.

**Look at:** Lower geo means and p90s; **Queens** (or any borough) geo mean near or below 8 min on
tiles.

**Spot-check (CLI):** geo mean ≈ **7.71** min, p90 ≈ **16.30** min, Cpk ≈ **0.02**.

**How to read this:** Best-case synthetic operations — geometric mean just under 8 minutes, but p90
still above 8, so the process is only **marginally** capable on the one-sided Cpk scale.

---

## Optional — Custom CSV upload

**Load:** **Upload Custom CSV** → use a file matching [`data/README.md`](../data/README.md) (five
boroughs, `call_received`, `on_scene_time`, optional conditions).

**Expect:** Rows outside boroughs or 0–300 min dropped; charts rebuild for the uploaded sample.

**How to read this:** Same statistics as built-in scenarios, on your own export shape.

---

## API spot-check (same math as `qc.py`)

```bash
curl -sS -X POST "http://localhost:8000/api/qc" \
  -H "Content-Type: application/json" \
  -d '{"response_times_min": [6, 8, 7, 9, 10]}'
```

With the app running (`./app/testme.ps1`), expect `imr.ucl_min` ≈ **13.21**, `capability.cpk` ≈ **0.027**
(see `tests/test_qc.py`).

---

## Related documents

| Document | Purpose |
|----------|---------|
| [`SPEC.md`](../SPEC.md) | Full method, inputs, outputs |
| [`data/README.md`](../data/README.md) | Codebook for the three CSVs |
| [`app/README.md`](../app/README.md) | Run locally, API, CLI, deploy |
| [`LR.md`](../LR.md) | Literature and process map |
