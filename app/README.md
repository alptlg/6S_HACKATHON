# NYC EMS Response Time Dashboard
**Cornell SYSEN 5300 · Six Sigma Hackathon · Team Chiblings**

A Six Sigma / SPC tool for NYC EMS response times, per borough: a log-scale I-MR control
chart, a 95% confidence interval on the geometric mean, and one-sided process capability (Cpk)
against the NFPA 1710 8-minute target. It ships as three things that share one statistics
module, `qc.py`:

| Piece | File | What it is |
|---|---|---|
| Dashboard | `static/index.html` | one self-contained HTML page (data and maps embedded, Chart.js from a CDN) |
| REST API | `main.py` | FastAPI app (`main:app`) that serves the dashboard and `POST /api/qc`; this is what Posit Connect runs |
| CLI | `cli.py` | prints the full SPC report for a CSV in the terminal |

All data is synthetic; see `data/README.md`.

**Live (Posit Connect):**  
https://connect.systems-apps.com/content/1d6d6d65-03cd-48d8-b0ac-8a07b1f3e27a/

Judge walkthrough: [`demo/README.md`](../demo/README.md).

---

## Run it

From the repo root, Python 3.12:

```bash
pip install -r app/requirements.txt
./app/testme.sh                 # Windows: .\app\testme.ps1
```

Open http://localhost:8000 for the dashboard and http://localhost:8000/docs for the API.

```bash
pytest tests                    # 16 tests: known answers, degenerate cases, API
```

---

## API

| Method | Path | Returns |
|---|---|---|
| `GET` | `/` | the dashboard (`static/index.html`) |
| `GET` | `/health` | `{"status": "ok"}`; the deploy workflow polls this |
| `POST` | `/api/qc` | the full `qc.run_qc` report for one list of response times |
| `GET` | `/docs` | interactive OpenAPI docs |

```bash
curl -X POST localhost:8000/api/qc -H 'Content-Type: application/json' \
     -d '{"response_times_min": [6, 8, 7, 9, 10]}'
```

The response has `descriptive`, `imr`, `ci`, `capability`, `alerts` and `warnings`. For
`[6, 8, 7, 9, 10]`: `imr.ucl_min` 13.21, `ci.geo_ci_low` 6.127, `capability.cpk` 0.027.
Fewer than 2 values, or any value ≤ 0, returns HTTP 422. An infinite Cpk (no spread) is sent as
`null`.

---

## CLI

```bash
python app/cli.py --scenario stable                      # all boroughs, full year
python app/cli.py --scenario delay --borough Manhattan --window 1mo
python app/cli.py --scenario fast --breakdown            # adds a per-borough table
python app/cli.py --csv data/my_data.csv --window 6mo
```

| Option | Values |
|---|---|
| `--scenario` / `--csv` | `stable`, `delay`, `fast`, or a path (one is required) |
| `--borough` | `all` (default), `Queens`, `Brooklyn`, `Manhattan`, `Bronx`, `Staten Island` |
| `--window` | `all` (default), `6mo`, `1mo`, `week`, `day`, counted back from the latest call |
| `--breakdown` | also print the per-borough table |

---

## Statistics (`qc.py`)

Response time is `response_time_min` from the CSV. If it is missing, the tool uses
`on_scene_time − call_received` (minutes). Rows outside 0–300 minutes are dropped.

| Function | Statistic |
|---|---|
| `compute_imr` | I-MR chart on `ln(RT)`: CL = mean of logs, UCL/LCL = CL ± 2.660 × MR̄, MR UCL = 3.267 × MR̄; shown in minutes via `exp()` |
| `compute_confidence_interval` | 95% t-interval on the arithmetic mean and on the mean of logs, back-transformed to a geometric-mean CI |
| `compute_capability` | one-sided `Cpu = (ln 8 − μ_log) / (3 σ_log)`, reported as Cpk; ≥ 1.33 capable, 1.0–1.33 marginal, < 1.0 not capable |
| `compute_descriptive` | n, mean, median, SD, min, p25, p75, p90, max, geometric mean; NFPA flag if mean or p90 > 8 min |
| `run_qc` | all of the above, plus alert and warning messages |

The Good / Fair / Bad split (< 8, 8–15, ≥ 15 min) is a display category, not a statistic.

---

## Rebuild the dashboard

`static/index.html` embeds a stratified sample of each scenario (80 calls per borough per
month = 4,800 calls) and base64 borough maps.

```bash
python app/pack_data.py --all    # CSVs -> compact JS arrays
python app/build_page.py         # template + data + maps -> index.html
```

The HTML template and map images are not in the repo, so for now `index.html` can only be
rebuilt on the machine that holds them.

---

## Known limitations

- **The dashboard computes its own statistics in JavaScript** (`computeStats` in `index.html`)
  instead of calling `/api/qc`. It uses the same formulas, but it runs on the 4,800-call
  sample and approximates the t critical value from a lookup table, so its numbers differ
  slightly from the CLI and API, which use every row.
- The dashboard's Cpk for constant data above 8 minutes shows +∞. `qc.py` returns −∞ (not
  capable) for that case.

---

## Deploy

Posit Connect runs `main:app` from this folder. A push to `main` that touches Python files,
`requirements.txt` or `manifest.json` triggers `.github/workflows/deploy-fastapi.yml`. That
workflow checks the committed manifest, imports `main:app`, publishes, and polls `/health`.

After changing `requirements.txt` or adding, renaming or deleting files in `app/`, rewrite the
manifest on your own machine and commit it:

```bash
./app/manifestme.sh      # rsconnect write-manifest fastapi . --entrypoint main:app --overwrite
```

`deployme.sh` deploys from your machine with `CONNECT_SERVER` and `CONNECT_API_KEY` set in a
gitignored `.env`.
