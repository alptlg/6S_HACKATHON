# Roadmap (RM) — Chiblings NYC EMS Zone Monitor

Simple plan for the hackathon build. Follow these **five steps in order**. Each step maps to tasks in `CONTRACT.yaml` (shown in parentheses).

**Already decided** (see `SPEC.md` and `docs/proposal.md`; all three files use the same names): Python, FastAPI, one HTML dashboard with Chart.js, statistics in `app/qc.py`, each borough's normal from 12 months of real NYC EMS data (`data/nyc_normals.py` -> `app/nyc_normals.json`), test data from `app/simulate.py`, deploy to **Posit Connect**, no logins, no database.

**Names used everywhere:** `incident_id`, `dispatch_time`, `on_scene_time`, `zone` (required); `call_received`, `traffic_level`, `available_units`, `priority` (optional); `response_time_min`, `call_to_dispatch_min`, `time_of_day`, `recent_call_volume` (derived by the tool); `simulated_special_cause` (test files only). Zones are the 5 NYC boroughs.

**Status (Fri night):** Steps 1-3 are built and tested (`pytest tests`: 38 passed). Next: Step 4 (deploy), then Step 5.

---

## Step 1 — Build `data/` and the codebook **(CONTRACT H-02)** — built

**Goal:** Three CSV files plus `data/README.md` so judges (and pytest) can run the tool on known stories.

**Done when:** `data/*.csv` exists (3 files) and the codebook describes every column and file (`CONTRACT` definition of done).

### Why this step matters (short research)

Real EMS agencies store **one row per call** in **CAD** (Computer-Aided Dispatch) with timestamps and **zones**; reports often show compliance **by zone** and use **percentiles**, not only monthly averages (see `LR.md` references [2], [4], [10]). We take each borough's **normal** from 12 months of real FDNY incidents (NYC Open Data, dataset `76xm-jjuj`, Oct 2025 - Sep 2026, 1,442,227 valid incidents) and **simulate** test files whose response times are drawn from those real distributions — no real incident rows or patient data in the repo.

The tool computes **`response_time_min = on_scene_time − dispatch_time`** (minutes) and orders each zone's calls by `dispatch_time`.

### How it is built

- **Generator:** `app/simulate.py` (fixed seeds 101 / 202 / 303). Regenerate from the repo root with `python -m app.simulate`. It lives in `app/` so the deployed app can rebuild the same samples without uploading CSVs.
- **Model:** normal response times are drawn from each borough's real NYC distribution; planted problems add minutes (traffic +1.5/+4.0, workload +3.0, 0-2 units +4.0). Values are in `data/README.md`.
- **Files** (problems planted from day 40, so days 1-14 are a clean baseline):

| File | Story | What the dashboard should show |
|------|-------|--------------------------------|
| `stable_operations.csv` | 60 days, 5 boroughs, nothing planted | all zones 🟢 in every period |
| `zone_patterns.csv` | from day 40: Queens high traffic; Bronx high workload + few units; Brooklyn all three; Manhattan 60 isolated extreme delays; Staten Island normal | Queens 🔴 Travel conditions; Bronx 🔴 Demand / resource pressure; Brooklyn 🔴 Combined stress; Manhattan 🟡 Unexplained special cause; Staten Island 🟢 |
| `minimal_input.csv` | only the 4 required columns, 21 days, bad rows, two non-borough zones | warnings, Harbor Unit judged on its own first 14 days, Ferry Terminal ⚪ Insufficient data, "factors unavailable", no crash |

### Judge quick test

- Which file proves **normal** control limits? `stable_operations.csv`
- Which file proves **zone** problems and the "why" patterns? `zone_patterns.csv`
- Which file proves the tool is **plug-and-play** with 4 columns? `minimal_input.csv`

---

## Step 2 — `app/qc.py` and tests **(CONTRACT H-03)** — built

**Goal:** All statistics in plain Python; **pytest passes**, including the SPEC **known answers** (raw and log-scale I-MR, p90, response time, workload) and degenerate cases (n = 1, constant times, missing columns, bad timestamps).

### Why this step matters (short research)

The method is **I-MR on ln(response time)** per borough with limits from the borough's **real 12-month NYC normal** (`SPEC.md` §4). The instructor demo `demos/pypackage/src/demotool/qc.py` shows the pattern: small functions, `Limits` named tuple, hand-checked tests. Course code uses **d2 = 1.128** for individuals charts, so 3/d2 = **2.66** and the MR chart UCL uses **D4 = 3.267**.

### What `qc.py` does (in order)

1. `prepare_incidents(df)` — checks the 4 required columns, drops bad rows with a warning, adds `response_time_min`, `call_to_dispatch_min`, `time_of_day`, `recent_call_volume`.
2. `borough_normal` + `limits_from_normal` — each borough's NYC normal gives its centerline, limits and normal p90 (log scale, shown in minutes); a non-borough zone uses `baseline_rows` + `imr_limits_log` on its first 14 days.
3. `period_window` — Live 3 h, Daily 24 h, Weekly 7 d, Monthly 30 d, Yearly 365 d, ending at the latest call. **Limits never move with the period.**
4. `zone_status` — 🔴 if calls above UCL are beyond chance, ≥ 3 and ≥ 3x the borough's normal rate, or 8 consecutive **daily medians** above the centerline, or the 99% bootstrap interval of p90 is above the normal p90 + 5%; 🟡 if calls above UCL are beyond chance or the 95% bootstrap interval of p90 is above normal p90 + 5%; else 🟢; ⚪ if a non-borough zone has < 20 baseline calls.
5. `compare_conditions` + `pattern_label` — Workload / Traffic / Units / Call-to-dispatch vs baseline, summarized as Travel conditions, High-demand pressure, Resource constraint, Demand / resource pressure, Combined operational stress, or Unexplained special cause.

### Known answers (tests in `tests/test_qc.py`)

1. **Raw minutes** `[6, 8, 7, 9, 10]`: mean 8.0, MR̄ 1.5, UCL 11.99, LCL 4.01.
2. **Log scale**, same data: centerline 7.87 min, UCL 13.21 min, LCL 4.69 min; MR UCL 0.6353 (log units).
3. **p90** of `[6, 8, 7, 9, 10]` = **9.6**.
4. Dispatch 17:42:10 → on scene 17:51:55 = **9.75 min**; calls at 10:00, 10:05, 10:14, 10:20 → `recent_call_volume` 0, 1, 2, 2.
5. Planted patterns: every expected status and pattern in the Step 1 table.

### Step 2 pitfalls (avoid losing points)

- Using one fixed target for every borough — real NYC p90s are 17-22 min and differ by borough; compare with each borough's normal.
- Computing limits from the period being checked — a bad month then hides inside its own wider limits; limits come from the NYC normal.
- Flagging a zone for **any** call above the UCL — with thousands of calls some exceed it by chance; compare with the expected count.
- Saying traffic **caused** a delay — conditions are "associated with / coincided with".

---

## Step 3 — FastAPI app and dashboard in `app/` **(CONTRACT H-04)** — built

**Goal:** One command starts the app; the page shows zone cards, the period selector and the zone detail, using only numbers from `qc.py`.

**Done when:** `app/testme` starts the server and the API returns the same numbers as `analyze_incidents()` for a `data/` file (`tests/test_api.py`).

### What exists

- `app/main.py` — thin HTTP layer: `/api/samples/{name}`, `/api/upload`, `/api/overview`, `/api/zone/{zone}`, `/api/incident`, `/api/download`, `/health`, `/docs`. One dataset in memory; no database.
- `app/static/` — `index.html`, `dashboard.js`, `styles.css`: sample buttons and CSV upload; `[Live | Daily | Weekly | Monthly | Yearly]`; zone cards (status, p90 vs normal p90, reason, pattern, conditions); zone detail (reasons, period vs baseline table, conditions table, I-MR chart with calls above the UCL in red, MR chart); incident-logging form with CSV download.
- Four-script contract: `testme.sh` / `testme.ps1`, `manifestme.sh`, `deployme.sh`, `README.md`.

### Step 3 pitfalls

- Putting statistics in `main.py` or `dashboard.js` — they only call `qc.py` and display.
- Forgetting **`pandas`/`numpy`** in `app/requirements.txt` (deploy crashes).

---

## Step 4 — Run locally, then deploy to Posit Connect **(CONTRACT H-06)**

**Goal:** Judges open a **public URL** (logged-out browser); the live app returns **HTTP 200** and the **same QC numbers** as pytest on at least one `data/` CSV.

**Done when:** `CONTRACT` H-06 definition of done — green GitHub Actions deploy (or a successful local `deployme.sh`), public URL loads the dashboard, and the zone overview still matches `analyze_incidents()`.

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
- Manual once: click **Zone patterns**, confirm the zone cards and one zone detail.

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

Connect prints a **content URL**. Open it in a browser, test `/`, `/health`, click a sample. Fix deploy logs before wiring CI.

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
  CONTENT_TITLE: Chiblings NYC EMS Zone Monitor
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
- Logged-out check: open URL in incognito, click **Zone patterns**, spot-check one number (e.g. Bronx Monthly p90) against pytest or `/api/overview`.

**4.10 — H-06 check-in**

- Set **`CONTRACT.yaml`** task **H-06** `status: done` and `result:` with: workflow run link or “local deploy”, public URL, and one line proving stats (e.g. “`/health` 200; zone_patterns Bronx p90 matches pytest”).
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
- **Bundling secrets or huge folders** inside `app/` — everything in `APP_DIR` goes up; keep data in repo `data/` only for Git; the bundle rebuilds the samples with `simulate.py` instead of shipping CSVs.
- **Assuming judges use the API key** — they use the **public** URL; fix Connect access policy, not auth in code (SPEC: no logins).
- **Green CI but 500 in browser** — open Connect **Logs** tab; often import error or missing static path.
- **HTTP 409 on first Actions deploy** — `CONTENT_NAME` collision; change `CONTENT_NAME` in workflow env.

**Reference docs in repo:** `.claude/skills/connect-publish/SKILL.md`, `README.md`, `workflows/deploy-fastapi.yml`; upstream pattern [timothyfraser/fastapi-connect-demo](https://github.com/timothyfraser/fastapi-connect-demo) (MIT).

---

## Step 5 — Demo walkthrough and docs **(CONTRACT H-05, H-07, H-08)**

**Goal:** `demo/README.md` steps for all three datasets (stable_operations, zone_patterns, minimal_input); top-level README for the tool; Devpost link; fresh clone + pytest + testme work.

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

**H-01** (fill `SPEC.md`) — done; SPEC, `docs/proposal.md` and this file use the same names.

---

## What we are *not* doing in Step 1

- Real 911 or hospital data  
- GPS or live feeds  
- Database tables (CSVs in Git only)  
- Patient names or addresses (use zone labels only)

---

*Team: Chiblings · Prompt #2 · Repo: `alptlg/6S_HACKATHON`*
