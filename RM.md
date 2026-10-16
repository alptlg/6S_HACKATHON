# Roadmap (RM) — Chiblings EMS Response Monitor

Simple plan for the hackathon build. Follow these **five steps in order**. Each step maps to tasks in `CONTRACT.yaml` (shown in parentheses).

**Already decided** (see `SPEC.md`): Python, FastAPI, one HTML dashboard with Chart.js, stats in `app/qc.py`, deploy to **Posit Connect**, no logins, no database.

---

## Step 1 — Build `data/` and the codebook **(CONTRACT H-02)**

**Goal:** Three small CSV files plus `data/README.md` so judges (and pytest later) can run the tool on known stories: normal ops, zone delays, occasional outliers.

**Done when:** `data/*.csv` exists (3 files) and the codebook describes every column and file (`CONTRACT` definition of done).

### Why this step matters (short research)

Real EMS agencies store **one row per call** in **CAD** (Computer-Aided Dispatch) with timestamps and **zones**; reports often show compliance **by zone** and use **percentiles**, not only monthly averages (see `LR.md` references [2], [4], [10]). We mimic that shape with **fake but realistic** data — no real 911 data.

Your tool will compute **response time = arrival_time − dispatch_time** (minutes). Charts need **time order** (sort by `call_received`). Zone flags use **I-MR on log(response time)** and **90th percentile vs 8 minutes** (`SPEC.md` §4).

---

### Step 1 substeps (how to build data + codebook)

**1.1 — Lock the column schema (do not add extra columns unless the team agrees)**

Use the same columns in all three CSVs (`SPEC.md` §3, §7):

| Column | Type | Notes |
|--------|------|--------|
| `incident_id` | string or int | Unique per row |
| `zone` | text | e.g. North, South, East, West, Central |
| `priority` | text | High, Medium, Low |
| `call_received` | datetime | `YYYY-MM-DD HH:MM:SS` |
| `dispatch_time` | datetime | After `call_received` |
| `arrival_time` | datetime | After `dispatch_time` |

`call_received` is **logged for realism**; **response time for charts** uses dispatch → arrival only.

**1.2 — Pick fixed “world settings” for all files**

- **Zones:** 4–5 names, used in every CSV (so bar charts compare the same places).
- **Date span:** e.g. 14–30 days of incidents so I-MR has enough points (aim **≥ 40 rows per file**, more is fine).
- **Priority mix:** mostly High/Medium for EMS demo; keep Low rare unless you test filtering later.
- **Clock rules:** every row must satisfy `call_received ≤ dispatch_time ≤ arrival_time`; response time **> 0** minutes.

**1.3 — Write a one-sentence “story” per file (from `SPEC.md`)**

| File | Story | What the dashboard should show |
|------|--------|--------------------------------|
| `normal_operations.csv` | Stable process, all zones similar | Few OOC points; zone alerts mostly quiet |
| `high_delay_operations.csv` | **South** and **West** slower for many days | Higher p90 in those zones; alerts name UCL and/or >8 min rule |
| `mixed_operations.csv` | Mostly normal + a few **very slow** calls | Individual points above UCL; interpret as special-cause spikes |

**1.4 — Decide how to generate numbers (synthetic, reproducible)**

Recommended approach for the hackathon:

- Use a **small Python script** (run once with `venv_sigma`, e.g. `data/generate_datasets.py`) with a **fixed random seed** so teammates get the same CSVs every time.
- **Normal file:** draw dispatch→arrival minutes from a tight distribution (e.g. log-normal with mean around 5–7 min) per zone, similar parameters.
- **High-delay file:** same as normal for North/East; **shift mean upward** for South/West after a chosen date (sustained shift, not one typo).
- **Mixed file:** mostly normal; **inject 3–8 extreme rows** (e.g. 15–25 min) spread across zones or concentrated in one zone — team choice, but document it in the codebook.

Optional checks while generating:

- After creating minutes, **back-compute** timestamps (call = dispatch − 1–3 min, arrival = dispatch + minutes) so CSVs look like real CAD exports.

**1.5 — Validate before committing**

- Open each CSV in pandas: no nulls in required fields, no duplicate `incident_id`, sort by `call_received`.
- Recompute response minutes and confirm **South/West** story in file 2 and **spikes** in file 3.
- Spot-check one row by hand (calculator).

**1.6 — Write `data/README.md` (the codebook)**

Include:

1. **Purpose** — synthetic data for Prompt #2; not real patients.
2. **Table per column** — name, unit, definition, role (predictor/outcome/id), allowed values.
3. **One subsection per CSV** — row count, date range, what behavior was planted, expected alert behavior.
4. **Collection in the real world** — 2–3 sentences: dispatcher records times in CAD; supervisor exports CSV (aligned with `LR.md` process map).
5. **Response time definition** — dispatch to arrival, minutes; link to `SPEC.md` §4.
6. **Generation note** — seed, script name, who ran it (reproducibility).

Hackathon rubric wants the same idea as a course **codebook table**: Variable | Unit | Definition & role.

**1.7 — Quick “judge story” check**

Teammate who did not write the data should answer:

- Which file proves **normal** control limits?
- Which file proves **zone** problems?
- Which file proves **single bad calls**?

If yes, Step 1 is ready for Step 2.

---

## Step 2 — `app/qc.py` and tests **(CONTRACT H-03)**

**Goal:** All statistics in plain Python; **pytest passes**, including SPEC **known-answer** (raw and log-scale I-MR) and degenerate cases (n=1, constant times, bad timestamps).

**Substeps (brief):**

- Implement validate → response times → log I-MR → zone summaries → alerts (`SPEC.md` §4).
- Put tests in `tests/`; run `pytest` from repo root with `venv_sigma`.
- Do **not** start the website until this step passes.

---

## Step 3 — Copy FastAPI demo to `app/` and wire the dashboard **(CONTRACT H-04)**

**Goal:** Copy `demos/fastapi/` → `app/`; add `app/qc.py`; serve **one HTML page** + Chart.js; routes for CSV upload and (optional) log form.

**Substeps (brief):**

- `app/app.py` only calls `qc.py` and returns JSON/HTML.
- `testme.sh` starts app on port 8000; numbers match Step 2 tests for at least one `data/` file.

---

## Step 4 — Run locally, then deploy to Posit Connect **(CONTRACT H-06)**

**Goal:** Judges open a **public URL**; app returns 200 and correct stats.

**Substeps (brief):**

- Local: `./app/testme.sh` (or Windows equivalent).
- `manifestme` → commit `manifest.json`; GitHub Actions workflow from connect-publish skill; repo secrets from event staff.
- Deploy **early**; fix deploy before adding polish.

---

## Step 5 — Demo walkthrough and docs **(CONTRACT H-05, H-07, H-08)**

**Goal:** `demo/README.md` steps for all three CSVs; top-level README for the tool; Devpost link; fresh clone + pytest + testme work.

**Substeps (brief):**

- For each CSV: exact click or URL, screenshot or numbers, one line “how to read this.”
- README: user, inputs, live URL, link to `demo/` and `LR.md`.
- Submit Devpost before **Oct 17, 1 PM ET** (on-campus).

---

## Quick map: five steps ↔ CONTRACT

| RM step | CONTRACT | Points theme |
|---------|----------|----------------|
| 1 | H-02 | Test data + codebook |
| 2 | H-03 | Valid QC statistics |
| 3 | H-04 | Working tool |
| 4 | H-06 | Live deploy |
| 5 | H-05, H-07, H-08 | Demo + docs + public repo |

**H-01** (fill `SPEC.md`) — mostly done; clean duplicate sections and leftover `FILL IN` when you touch SPEC again.

---

## What we are *not* doing in Step 1

- Real 911 or hospital data  
- GPS or live feeds  
- Database tables (CSVs in Git only)  
- Patient names or addresses (use zone labels only)

---

*Team: Chiblings · Prompt #2 · Repo: `6s_hackathon`*
