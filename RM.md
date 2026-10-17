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

**Done when:** `pytest tests` passes from repo root (`CONTRACT` H-03); a teammate can explain every number using `SPEC.md` §4.

### Why this step matters (short research)

Hackathon grading puts **25 points** on “valid QC analysis” — not on chart colors (`docs/criteria.md`). The repo’s **stats-first-steering** skill says: write the method in words, implement **one plain function**, **verify with known answers**, then wrap the API (`.claude/skills/stats-first-steering/SKILL.md`).

Your method is **I-MR on log(response time)** with **zone percentiles** and **8-minute** alert rule (`SPEC.md` §4). The instructor demo `demos/pypackage/src/demotool/qc.py` shows the pattern: small functions, `Limits` named tuple, hand-checked tests in `demos/pypackage/tests/test_qc.py`. SYSEN course code uses moving-range constants **d2 = 1.128** for individuals charts (`sysen/functions/functions_process_control.py` — same idea as the demo).

**Important:** `app/qc.py` must **not** import FastAPI, pandas in the API layer is OK inside qc if you prefer — but keep **formulas testable** without starting a server. Step 3 only **calls** what you prove here.

---

### Step 2 substeps (how to build statistics + tests)

**2.1 — Create `app/qc.py` early (stats-only, no website yet)**

- Add folder `app/` if it does not exist; put **`app/qc.py`** here first (you can copy `demos/fastapi/` later in Step 3).
- Allowed imports: `math`, `statistics`, `numpy`, `pandas` (pandas only for table hygiene — sorting, timestamps, groupby).
- Return plain Python types: `dict`, `list`, `float`, small **`NamedTuple`** / dataclass (like demo `Limits`).

**2.2 — Response time from the Step 1 schema**

- Function: e.g. `add_response_minutes(df)` → adds `response_min` = `(arrival_time - dispatch_time)` in minutes.
- Sort by `call_received` before any time-series chart.
- Drop or reject rows with nonpositive or missing intervals.

**2.3 — Validation layer (assumptions from SPEC §4)**

- Function: e.g. `validate_incidents(df)` → `(clean_df, warnings: list[str])`.
- Check: required columns, duplicate `incident_id`, timestamp order, finite times, optional minimum row count (e.g. ≥ 2 for I-MR, suggest **≥ 8 per zone** before zone-specific I-MR).
- If checks fail badly, downstream functions should **warn** rather than silently plot (matches SPEC “display a warning”).

**2.4 — Descriptive summaries (for dashboard section 1)**

- Function: e.g. `response_summary(times)` → mean, median, stdev, **p90, p95** using **`numpy.percentile(..., method="linear")`** (SPEC decision).
- Function: e.g. `zone_summaries(df)` → same stats **by zone** for bar charts.

**2.5 — Log-scale I-MR limits (core graded statistic)**

Work on **`y = ln(response_min)`** in order (after sort):

| Quantity | Formula (log units) | Notes |
|----------|---------------------|--------|
| Centerline | mean(`y`) | Display in minutes: `exp(center_log)` ≈ geometric mean |
| Moving ranges | `|y_i - y_{i-1}|` | Need ≥ 2 points |
| MR̄ | mean of moving ranges | |
| Individuals UCL/LCL | center ± **2.66 × MR̄** | 2.66 ≈ 3/d2 for n=2 individuals chart |
| MR chart UCL | **3.267 × MR̄** | LCL = 0 for moving range |

Functions to implement (names up to you):

- `imr_limits_log(values)` → limits in **log** and **minute** scale for display.
- `imr_series(values, limits)` → each point’s `y`, MR, and **OOC flag** (above UCL or below LCL on the **log** individuals chart).

**Known-answer tests (from SPEC — must pass):**

1. **Raw minutes** `[6, 8, 7, 9, 10]`: mean 8.0, MR̄ 1.5, UCL 11.99, LCL 4.01 (unlogged textbook check — proves you understand MR).
2. **Log-scale** same data: centerline ≈ 7.87 min, UCL ≈ 13.21 min, LCL ≈ 4.69 min; MR UCL ≈ 0.6353 in log units.
3. **p90** of `[6, 8, 7, 9, 10]` = **9.6** (> 8 → flag example).

**2.6 — Zone alerts (dashboard section 4)**

- Function: e.g. `zone_alerts(df, global_limits, ...)`.
- **Flag a zone** if **any** call in that zone is above the **individuals UCL** (log-based), **or** zone **p90 > 8** minutes (NFPA-style target in SPEC).
- Return **which rule fired** (`"ucl"`, `"p90"`, or both) so the UI text is explainable.

**2.7 — One orchestrator for Step 3 API (optional but helpful)**

- Function: e.g. `analyze_incidents(df) -> dict` calling 2.2–2.6 in order.
- Structure JSON-friendly: summaries, chart series, limits, alerts, warnings.
- **No HTTP** in this file — FastAPI will call this in Step 3.

**2.8 — Write `tests/test_qc.py` at repo root**

Mirror `demos/pypackage/tests/test_qc.py` style:

| Test bucket | Example |
|-------------|---------|
| Hand-checked | SPEC `[6,8,7,9,10]` raw + log I-MR + p90 |
| Degenerate | one point; constant times; empty after validation |
| Bad input | bad timestamps, duplicates, negative response |
| Planted signal | load `data/high_delay_operations.csv` → South/West p90 > 8; `mixed_operations.csv` → at least one OOC |

Run: `conda activate venv_sigma` → from repo root: **`pytest tests`**.

**2.9 — Cross-check against Step 1 data (sanity, not submission)**

- Load each CSV; print zone p90 and alert list — confirm stories match `data/README.md` before building the UI.

**2.10 — H-03 check-in (when green)**

- Quote pytest output in `CONTRACT.yaml` task **H-03** `result:` line.
- Team can recite: “I-MR on log response time; 2.66 and 3.267 constants; zone flag = UCL or p90 > 8.”

**2.11 — Stop line**

- Do **not** copy FastAPI, HTML, or Chart.js until **all** Step 2 tests pass (stats-first-steering rule).

---

### Step 2 pitfalls (avoid losing points)

- Using **sample stdev × 3** for control limits instead of **MR̄/d2** (wrong chart type).
- Mixing **spec limit 8 min** with **UCL** — 8 minutes is a **policy target**, not the control limit.
- Computing limits on the **whole** series including planted shifts you want to detect (limits too wide) — for demo, document that limits use **all uploaded points** unless you split baseline later.
- Putting formulas inside `app.py` / JavaScript — judges want **`app/qc.py` + tests**.

---

## Step 3 — Copy FastAPI demo to `app/` and wire the dashboard **(CONTRACT H-04)**

**Goal:** A **working tool** judges can open locally: one dashboard page, CSV upload, numbers that **match Step 2 / pytest** on `data/` files.

**Done when:** `app/testme` starts the server; upload or API call on `data/normal_operations.csv` returns the **same summary / limits** as `analyze_incidents()` in tests (`CONTRACT` H-04).

### Why this step matters (short research)

H-04 is **25 points** for “does it run?” — not for extra features (`docs/criteria.md`). The hackathon **four-script contract** lives in `demos/fastapi/README.md`: `testme`, `manifestme`, `deployme`, `README.md`. Posit Connect expects **`app.py` or an explicit entrypoint**, `requirements.txt`, `manifest.json`, `.python-version` inside **`APP_DIR`** (Step 4 sets `APP_DIR: 'app'` in the workflow).

Your SPEC chose **one HTML page + Chart.js CDN** (no React build). The demo `app.py` is intentionally **thin** — same rule as `demos/pypackage`: **all statistics stay in `app/qc.py`**. JavaScript only **plots JSON** from the API.

**Layout note:** You already have **`app/qc.py`** (Python package `app`). Avoid naming the FastAPI file `app.py` inside that folder (clashes with `import app.qc`). Use **`app/main.py`** with `app = FastAPI()` and entrypoint **`main:app`** for uvicorn/manifest.

---

### Step 3 substeps (how to build API + dashboard)

**3.1 — Merge demo files into `app/` without touching `qc.py`**

Copy from `demos/fastapi/` into `app/`:

| From demo | Into `app/` |
|-----------|-------------|
| `requirements.txt` | extend with `pandas`, `numpy` (pin with `==`) |
| `.python-version` | `3.12` |
| `testme.sh`, `manifestme.sh`, `deployme.sh` | adjust entrypoint to **`main:app`** |
| `README.md` | short app-specific run instructions |

Add **`app/main.py`** (new) instead of copying demo `app.py` verbatim. Keep **`app/qc.py`** as-is.

**3.2 — Pin dependencies in `app/requirements.txt`**

Minimum:

- `fastapi`, `uvicorn[standard]` (demo pins)
- `pandas`, `numpy` (for `qc.py`)

Install in `venv_sigma`: `pip install -r app/requirements.txt`. Step 4 deploy uses **only** this file.

**3.3 — FastAPI routes (thin wrappers only)**

Suggested endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Serve dashboard HTML (or redirect to `/static/index.html`) |
| `GET` | `/health` | `{ "status": "ok" }` for smoke tests |
| `POST` | `/api/analyze` | `UploadFile` CSV → `pd.read_csv` → `analyze_incidents()` → JSON |
| `POST` | `/api/incident` | JSON body with one row → append logic optional → return updated analysis |
| `GET` | `/docs` | FastAPI OpenAPI (demo bonus for judges) |

Rules:

- **No** control-limit math in `main.py` or in the browser.
- Return **`analyze_incidents` dict** (or a stable subset) so Step 5 demo can cite fields.

**3.4 — Dashboard UI (`app/static/index.html` + optional `app/static/dashboard.js`)**

One scrollable **supervisor dashboard** (`SPEC.md` §6):

1. **Upload** — file input → `POST /api/analyze`
2. **Summary cards** — mean, median, SD, p90, p95 from `summary`
3. **Two SPC charts (Chart.js)** — Individuals + Moving Range from `chart_points` + `limits_log` (display minutes on I-chart; MR in log units or labeled axis)
4. **Zone bar chart** — p90 or mean by zone from `zone_summaries`
5. **Alerts list** — `zone_alerts` messages (`ucl`, `p90`)
6. **Warnings** — show `warnings` array if present
7. **Interpretation** — 1–2 static sentences under each section (“what to do if red”)

Load Chart.js from a **CDN** (SPEC). No Node/npm build.

**3.5 — Incident logging form (minimal)**

HTML form: zone, priority, three timestamps, optional id → POST `/api/incident`.

Simplest v1: server holds **in-memory list** for the session (lost on restart — OK per SPEC “no database”). Better v1: analyze **uploaded CSV only** and ship logging in a follow-up if time is short — but SPEC lists logging; at least one working path before submit.

**3.6 — Wire static files in FastAPI**

Use `StaticFiles` for `app/static/` and/or `HTMLResponse` for `/`. Enable CORS only if you split front/back hosts (not needed for single-page same origin).

**3.7 — Local run scripts (Windows + bash)**

- **`app/testme.sh`:** `cd` to `app/`, `uvicorn main:app --host 0.0.0.0 --port 8000`
- **`app/testme.ps1` (optional):** same for Windows teammates

Verify: open `http://localhost:8000`, upload `data/normal_operations.csv`, see charts.

**3.8 — Cross-check numbers vs Step 2 (required for H-04)**

In a Python shell or test:

```python
import pandas as pd
from app.qc import analyze_incidents
df = pd.read_csv("data/normal_operations.csv")
direct = analyze_incidents(df)
# POST same file to /api/analyze → JSON must match direct for summary, limits_log, n_incidents
```

Optional: add **`tests/test_api.py`** with `httpx` + `TestClient` if time permits — not required if manual check is documented in H-04 `result`.

**3.9 — `app/README.md` (four-script contract)**

Document: purpose, endpoints, **`./testme.sh`**, `./manifestme.sh`, `./deployme.sh`, link to repo `SPEC.md`.

**3.10 — H-04 check-in**

- Quote: server start command + one example JSON field (e.g. `limits_log.ucl_min`) matching pytest.
- Do **not** start Step 4 until upload works once locally.

---

### Step 3 pitfalls

- Renaming or breaking **`app/qc.py`** imports used by **`tests/test_qc.py`** (run `pytest` after every app change).
- Putting **`APP_DIR: '.'`** in deploy workflow while the app lives in **`app/`** (manifest not found — fix in Step 4).
- Chart.js computing limits in the browser instead of displaying server values.
- Forgetting **`pandas`/`numpy`** in `app/requirements.txt` (deploy crashes).

---

## Step 4 — Run locally, then deploy to Posit Connect **(CONTRACT H-06)**

**Goal:** Judges open a **public URL** (logged-out browser); the live app returns **HTTP 200** and the **same QC numbers** as pytest on at least one `data/` CSV.

**Done when:** `CONTRACT` H-06 definition of done — green GitHub Actions deploy (or a successful local `deployme.sh`), public URL loads the dashboard, upload/analysis still matches `analyze_incidents()`.

**Points context:** H-06 does not add a separate rubric line; it **protects the 25 “working tool” points** — if judges cannot open your app, H-04 does not count (`CONTRACT.yaml`).

### Why this step matters (short research)

Course materials treat deploy as **parallel to building**, not after polish (`docs/start.md`: deploy early; `docs/schedule.md`: publish to Connect during the event). Instructor workflow lives in **`.claude/skills/connect-publish/`** — copy **`workflows/deploy-fastapi.yml`** and **`scripts/connect-publish-async.sh`**, do **not** invent a workflow from scratch.

**Two paths to the same URL:**

| Path | When to use |
|------|-------------|
| **Local** `app/deployme.sh` | Fastest **first** public URL at the hackathon (needs `CONNECT_SERVER` + `CONNECT_API_KEY` in a **gitignored** `.env`) |
| **GitHub Actions** | Every push to `main` redeploys without someone running a script |

Both require a **committed `app/manifest.json`** written on a **developer machine**, never regenerated on the CI runner (see skill `SKILL.md` — manifest is an environment **fingerprint**; `rsconnect deploy` on Actions often breaks builds).

**Your layout vs the demo:** Starter workflow defaults assume `APP_DIR: '.'` and entrypoint **`app:app`**. Chiblings use **`APP_DIR: 'app'`** and **`main:app`** (`app/main.py`). The workflow `env:` block is the only file you should need to edit besides copying paths.

**Public access:** Publisher key is for **deploy**, not for judges. In Posit Connect, set the content item so **Anyone** (or the course default) can open the URL without logging in — matches H-06 “logged-out browser.”

---

### Step 4 substeps (how to deploy)

**4.1 — Gate: local app still green**

- From repo root: `pytest tests` (all green).
- Start server: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` or `.\app\testme.ps1`.
- Manual once: upload `data/normal_operations.csv`, confirm charts and summary.

Do not deploy until this works — Connect failures are harder to debug than laptop errors (`connect-publish` skill: run `testme` before `manifestme`).

**4.2 — Fix imports for the Connect bundle (Chiblings-specific)**

Connect runs with **working directory = `app/`** and entrypoint **`main:app`**. That is **not** the same as repo-root `uvicorn app.main:app`.

Smoke test (must pass before manifest):

```powershell
cd app
python -c "import importlib; getattr(importlib.import_module('main'), 'app'); print('ok')"
```

If you see `ModuleNotFoundError: No module named 'app'`, change **`app/main.py`** to import statistics with a **sibling** import, e.g. `from qc import analyze_incidents`, not `from app.qc import ...`. Keep **`tests/`** importing `from app.qc` / `from app.main` from **repo root** — both layouts can coexist.

Re-run `pytest tests` after any import change.

**4.3 — Repo hygiene for manifests**

At **repo root**, add **`.gitattributes`** (if missing):

```
* text=auto eol=lf
```

Confirm **`.env`** is gitignored and **`git status`** shows no secrets before any commit.

**4.4 — Pin Python version file**

- **`app/.python-version`** should hold **major.minor only**, e.g. `3.12` (no `3.12.14`, no stray spaces).
- Create/edit in the **editor**, not PowerShell `echo` (CRLF breaks Actions — see connect-publish README).

**4.5 — Write and commit `manifest.json` (on your laptop)**

From **`app/`** (Git Bash on Windows is fine):

```bash
python -m pip install rsconnect-python
./manifestme.sh    # rsconnect write-manifest fastapi . --entrypoint main:app
```

Checklist before commit:

| Check | How |
|-------|-----|
| `appmode` | `jq -r '.metadata.appmode' app/manifest.json` → **`python-fastapi`** |
| Entrypoint | **`main:app`** |
| Python | Manifest `python.version` matches **`app/.python-version`** (e.g. 3.12.x vs `3.12`) |
| Files listed | Includes `main.py`, `qc.py`, `requirements.txt`, `static/*`, etc. |
| No secrets | No `.env`, no API keys in the bundle folder |

**Regenerate manifest** after every change to `app/requirements.txt` or files the manifest tracks.

**4.6 — First deploy locally (optional but recommended at the event)**

Event staff hand out **`CONNECT_SERVER`** (full `https://...` URL) and **`CONNECT_API_KEY`**. Store only in **gitignored `.env`** at repo root or `app/`:

```
CONNECT_SERVER=https://...
CONNECT_API_KEY=...
```

```bash
cd app
source ../.env   # bash; on Windows load env vars another safe way
./deployme.sh
```

Connect prints a **content URL**. Open it in a browser, test `/`, `/health`, upload CSV. Fix deploy logs before wiring CI.

**4.7 — GitHub repo secrets (for Actions)**

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|--------|
| `CONNECT_SERVER` | Same server URL from staff |
| `CONNECT_API_KEY` | Your publisher key |

Never paste these in chat, commits, or README. H-08 requires a **public GitHub repo** — secrets live only in GitHub settings.

**4.8 — Copy the FastAPI workflow + publish script**

Into your repo:

```
.github/workflows/deploy-fastapi.yml   ← from .claude/skills/connect-publish/workflows/
.github/scripts/connect-publish-async.sh   ← from .claude/skills/connect-publish/scripts/
```

Edit **only** the `env:` block at the top of `deploy-fastapi.yml`:

```yaml
env:
  APP_DIR: 'app'                      # NOT '.' — your FastAPI folder
  CONTENT_NAME: chiblings-6s-hackathon-fastapi   # optional; must be unique on server
  CONTENT_TITLE: Chiblings EMS Response Monitor
  HEALTH_PATH: '/health'              # you implemented GET /health; demo used /docs
```

Workflow also:

- Verifies committed manifest (never rewrites it).
- Runs `pip install -r requirements.txt` and **imports `main:app`** inside `APP_DIR` (catches 4.2 mistakes).
- Publishes via **curl** to Connect API (no `rsconnect` on the runner).
- Polls until **`HEALTH_PATH`** returns **200** (with publisher key in CI — judges use anonymous access per 4.9).

Push to **`main`** (or **Actions → Run workflow**). Watch lines prefixed **`connect>`** for server build errors.

**4.9 — Make the URL judge-ready**

In Posit Connect UI for your app:

- Confirm **Access** allows viewers without a Connect login (course instructions at deploy time).
- Copy the **public content URL** into team notes (Step 5 goes in `README.md` and Devpost).
- Logged-out check: open URL in incognito, load dashboard, upload `data/normal_operations.csv`, spot-check one number (e.g. mean response time) against pytest or `/api/analyze`.

**4.10 — H-06 check-in**

- Set **`CONTRACT.yaml`** task **H-06** `status: done` and `result:` with: workflow run link or “local deploy”, public URL, and one line proving stats (e.g. “`/health` 200; normal_operations mean matches pytest”).
- Team rule: **UI polish after first green deploy** — redeploy by pushing to `main` or re-running `deployme.sh`.

**4.11 — Iterate after Step 4 (expected)**

Local dev unchanged (`testme.ps1`). Each meaningful change: test locally → if deps changed, re-run **`manifestme.sh`** and commit manifest → push → wait for green Actions. Same URL, new version.

---

### Step 4 pitfalls

- **`APP_DIR: '.'`** while the app lives in **`app/`** — manifest check fails or bundles the wrong tree.
- **Entrypoint `app:app`** — wrong for Chiblings; use **`main:app`** and re-write manifest.
- **`from app.qc import ...` in `main.py`** — works at repo root with `uvicorn app.main:app`, **fails** on Connect with `main:app` from `app/` (see 4.2).
- **Manifest generated in GitHub Actions** or on a machine that never ran the app — stale/wrong fingerprint; always write on a dev laptop after `testme` works.
- **Windows CRLF in `manifest.json`** — add `.gitattributes`, re-write manifest, recommit.
- **`.python-version` mismatch** — e.g. file says `3.11` but manifest says `3.12`.
- **Forgetting to regenerate manifest** after adding a package to `requirements.txt` — Connect install step fails.
- **Bundling secrets or huge folders** inside `app/` — everything in `APP_DIR` goes up; keep data in repo `data/` only for Git, not required in bundle unless you intentionally ship sample CSVs in `static/`.
- **Assuming judges use the API key** — they use the **public** URL; fix Connect access policy, not auth in code (SPEC: no logins).
- **Green CI but 500 in browser** — open Connect **Logs** tab; often import error or missing static path.
- **HTTP 409 on first Actions deploy** — `CONTENT_NAME` collision; change `CONTENT_NAME` in workflow env.

**Reference docs in repo:** `.claude/skills/connect-publish/SKILL.md`, `README.md`, `workflows/deploy-fastapi.yml`; upstream pattern [timothyfraser/fastapi-connect-demo](https://github.com/timothyfraser/fastapi-connect-demo) (MIT).

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
