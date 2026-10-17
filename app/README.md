# NYC EMS Zone Monitor: app (FastAPI)

Statistical early warning for EMS dispatch-to-on-scene response times. Statistics live in
`qc.py`; `main.py` is only the HTTP layer; `static/` is the dashboard (plain HTML + Chart.js);
the three test datasets are the `*_synthetic.csv` files in `../data/` (see `../data/README.md`);
`nyc_normals.json` holds each borough's normal from 12 months of real NYC EMS incidents (built by
`../data/nyc_normals.py`).

## Run locally

From the repo root, with a virtual environment active (`.venv`, or the conda env `venv_sigma`):

```bash
pip install -r app/requirements.txt
bash app/testme.sh        # Windows PowerShell: .\app\testme.ps1
```

Open http://localhost:8000, then click a sample (Stable operations, Zone patterns, Minimal
input) or upload a CSV.

## Functions in `qc.py`

| Function | Input | Output |
|---|---|---|
| `prepare_incidents(df)` | incident DataFrame (4 required columns, optional extras) | clean rows sorted by `dispatch_time` with `response_time_min`, `call_to_dispatch_min`, `time_of_day`, `recent_call_volume`; list of warnings |
| `imr_limits_log(values)` | response times (min), at least 2 | centerline, UCL, LCL (log and minutes), average MR, MR UCL |
| `control_limits_raw(values)` | response times (min) | I-MR limits on raw minutes (known-answer check only) |
| `percentile_linear(values, q)` | numbers, q in 0-100 | percentile, linear interpolation |
| `response_summary(values)` | response times | mean, median, SD, p90, p95, n |
| `recent_call_volume(times, zones)` | dispatch times, zones | calls in the same zone during the previous 15 min |
| `period_window(df, period)` | clean rows, `live`/`daily`/`weekly`/`monthly`/`yearly` | rows in the last 3 h / 24 h / 7 / 30 / 365 days |
| `baseline_rows(zone_df)` | one zone's rows | its first 14 days (non-borough zones; conditions baseline) |
| `load_normals()`, `borough_normal(zone)` | zone name (case-insensitive borough) | the borough's NYC normal, or None |
| `limits_from_normal(normal)` | a borough normal | its log I-MR limits |
| `bootstrap_percentile_ci(values, q, confidence)` | numbers | bootstrap interval for a percentile (1,000 resamples, fixed seed) |
| `zone_status(times, days, limits, normal_p90, normal_rate)` | period response times, their days, normal limits | status, reasons, calls above UCL, expected by chance, p90 and its bootstrap intervals, daily run |
| `compare_conditions(baseline, window)` | baseline rows, period rows | Workload / Traffic / Units / Call-to-dispatch vs baseline, time-of-day pattern |
| `pattern_label(status, conditions)` | status, conditions | Travel conditions, Demand / resource pressure, ... |
| `analyze_zone(clean, zone, period)` | one zone | everything the zone detail shows (optionally chart points) |
| `analyze_incidents(df, period)` | raw DataFrame | the zone overview (one card per zone) |

## API

| Method | Path | Description |
|---|---|---|
| GET | `/` | dashboard |
| GET | `/health` | smoke check |
| GET | `/api/samples` | the three dataset keys and the CSV files they map to |
| POST | `/api/samples/{name}?period=` | load one of the three `*_synthetic.csv` files |
| POST | `/api/upload?period=` | upload a CSV, return the overview |
| GET | `/api/overview?period=` | zone cards for the loaded data |
| GET | `/api/zone/{zone}?period=` | zone detail with chart points |
| GET | `/api/charts/boxplot/{zone}?period=&group=` | Tukey box plots by `weekday` (default) or `month`, on ln(minutes) |
| GET | `/api/charts/heatmap/{zone}?period=&stat=&minimum=` | weekday × hour grid of the `p90` (default) or `median`; cells under `minimum` calls return `null` |
| POST | `/api/incident?period=` | add one incident (kept in memory for this session) |
| GET | `/api/download` | loaded data, including logged incidents, as CSV |
| GET | `/docs` | interactive API docs |

`period` is `live`, `daily`, `weekly`, `monthly` (default) or `yearly`. The two `/api/charts/`
endpoints are descriptive: they cannot change a zone's status. The heatmap has 168 cells, so one
zone fills it at `yearly`; at shorter periods most cells have fewer than `minimum` calls and come
back as `null` ("not enough calls"), which the page renders in grey.

## Posit Connect

**Entrypoint:** `main:app` · **Python:** `3.12` (`.python-version` must match `manifest.json`).

### GitHub Actions (recommended)

1. Repo **Settings -> Secrets -> Actions**: add `CONNECT_SERVER` and `CONNECT_API_KEY` (from event staff).
2. Push to `main`: `.github/workflows/deploy-fastapi.yml` ships `app/manifest.json`.
3. Re-run `manifestme.sh` and commit whenever `requirements.txt` or bundled files change.

### Local deploy

Gitignored `.env` at the repo root with `CONNECT_SERVER` and `CONNECT_API_KEY`, then:

```bash
cd app
./manifestme.sh
./deployme.sh
```

In Connect, set access so judges can open the URL without logging in.

## Tests

From the repo root: `pytest tests` (statistics known answers, degenerate cases, planted patterns,
API smoke tests).
