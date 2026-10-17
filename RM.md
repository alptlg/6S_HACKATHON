# Roadmap (RM) — Chiblings NYC EMS Response Time Dashboard

The hackathon plan in five steps. Each step maps to tasks in `CONTRACT.yaml` (shown in
parentheses).

**Decided** (see `SPEC.md` and `docs/proposal.md`): Python 3.12, FastAPI, one self-contained
HTML dashboard with Chart.js, statistics in `app/qc.py` (log I-MR, 95% CI, Cpk against the NFPA
1710 8-minute target), three synthetic year-long scenarios, a CLI in `app/cli.py`, deployment
to **Posit Connect**, no logins and no database.

**Status (Sat Oct 17):** Steps 1-3 and docs (Step 5 README/demo/codebook) are aligned with the
shipped dashboard. `pytest tests` gives 16 passed. Live URL on Connect (Step 4). Submit Devpost
(H-08) and check in `CONTRACT.yaml` when done.

---

## Step 1 — `data/` and the codebook **(CONTRACT H-02)** — built

Three synthetic CSVs, 24,000 calls each, 2026-01-01 to 2026-12-31, 5 boroughs:

| File | Story | Full-year result (`app/cli.py`) |
|---|---|---|
| `stable_operations_2026_24000_synthetic.csv` | normal operations | geo mean 11.12 min, p90 23.23, Cpk −0.18 |
| `highDelayAlex_2026_24000_synthetic.csv` | heavy delays citywide | geo mean 19.58, p90 48.40, Cpk −0.43 |
| `noDelayAlexData_2026_24000_synthetic.csv` | fast, optimal conditions | geo mean 7.71, p90 16.30, Cpk 0.02 |

Codebook: [`data/README.md`](data/README.md).

---

## Step 2 — `app/qc.py` and tests **(CONTRACT H-03)** — built

One function per statistic: `compute_imr`, `compute_confidence_interval`,
`compute_capability`, `compute_descriptive`, and `run_qc` to run them all.

`tests/test_qc.py` checks the hand-worked known answer for [6, 8, 7, 9, 10]: I-MR centerline
7.87, UCL 13.21, LCL 4.69 min; MR UCL 0.6353; geometric-mean CI [6.127, 10.115]; Cpk 0.0265;
p90 9.6. It also covers degenerate cases: constant data below and above 8 min, n = 1, an empty
list, and zero or negative times.

**Pitfalls:**
- Limits come from the data being charted (Phase I). A borough that is slow all year has wide
  limits and few out-of-control points. Read Cpk for that.
- Conditions "coincided with" out-of-control calls; they did not "cause" them.

---

## Step 3 — FastAPI app, dashboard and CLI in `app/` **(CONTRACT H-04)** — built

- `app/main.py` (`main:app`): `/` serves the dashboard, `GET /health`, `POST /api/qc`, `/docs`.
- `app/static/index.html`: self-contained page with scenario buttons, CSV upload, time windows,
  borough cards, and per-borough I-MR, CI and Cpk views. Rebuilt with `pack_data.py` and
  `build_page.py`.
- `app/cli.py`: terminal report, `--scenario`, `--borough`, `--window`, `--breakdown`.
- Four-script contract: `testme.sh` / `testme.ps1`, `manifestme.sh`, `deployme.sh`, `README.md`.

**Known gap (costs points under "valid QC analysis"):** the dashboard computes its statistics in
JavaScript on a 4,800-call sample instead of calling `POST /api/qc`. Fix: have `index.html`
fetch `/api/qc` per borough and window, or at least show which numbers come from `qc.py`.

---

## Step 4 — Deploy to Posit Connect **(CONTRACT H-06)**

The workflow `.github/workflows/deploy-fastapi.yml` runs on every push to `main` that touches
Python files, `requirements.txt` or `manifest.json`. It:

1. checks the committed `app/manifest.json` (appmode `python-fastapi`, entrypoint `main:app`,
   Python matching `app/.python-version`);
2. installs `app/requirements.txt` and imports `main:app`;
3. checks the `CONNECT_SERVER` and `CONNECT_API_KEY` repo secrets;
4. publishes, then polls `/health` until it returns 200.

**Checklist:**
- Before pushing: `pytest tests`, then the smoke test from `app/`:
  `python -c "import main; main.app"`.
- After changing `requirements.txt` or adding, renaming or deleting files in `app/`: run
  `./app/manifestme.sh` **on your own machine** and commit `manifest.json`. A manifest that
  lists a deleted file fails the publish step.
- Every package `qc.py` imports must be in `requirements.txt`. A missing `scipy` broke the
  Oct 17 deploys.
- Secrets live only in GitHub repo secrets or a gitignored `.env`, never in a file.
- In Connect, set access so anyone can open the URL without logging in, then check it in a
  private browser window.
- Check in H-06 with the workflow run link and the public URL.

---

## Step 5 — Demo walkthrough and docs **(CONTRACT H-05, H-07, H-08)**

- [`demo/README.md`](demo/README.md): each scenario — live Connect URL, clicks, CLI spot-checks,
  one-line interpretation.
- [`README.md`](README.md): tool front door — user, inputs, live URL, links to `demo/`, `app/`,
  `SPEC.md`, `LR.md`.
- Fresh clone: `pip install -r app/requirements.txt && pytest tests` passes.
- Update `CONTRACT.yaml` task results when the team checks in.
- Submit on Devpost: repo + https://connect.systems-apps.com/content/1d6d6d65-03cd-48d8-b0ac-8a07b1f3e27a/
  before **Oct 17, 1 PM ET** (on-campus).

---

## Quick map: five steps ↔ CONTRACT

| RM step | CONTRACT | Points theme |
|---------|----------|----------------|
| 1 | H-02 | Test data + codebook |
| 2 | H-03 | Valid QC statistics |
| 3 | H-04 | Working tool |
| 4 | H-06 | Live deploy |
| 5 | H-05, H-07, H-08 | Demo + docs + public repo |

---

*Team: Chiblings · Prompt #2 · Repo: `alptlg/6S_HACKATHON`*
