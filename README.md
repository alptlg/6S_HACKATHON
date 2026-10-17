# NYC EMS Response Time Dashboard

**Cornell SYSEN 5300 · Six Sigma Hackathon · Team Chiblings · Prompt #2**

Statistical quality dashboard for NYC EMS **dispatch-to-on-scene** response times by borough: log-scale
**I-MR** control charts, **95% confidence interval** on the geometric mean, and one-sided **Cpk**
against the NFPA 1710 **8-minute** target. Optional condition columns support traffic, unit, and
priority views for out-of-control calls.

| | |
|---|---|
| **Live app** | https://connect.systems-apps.com/content/1d6d6d65-03cd-48d8-b0ac-8a07b1f3e27a/ |
| **Public repo** | https://github.com/alptlg/6s_hackathon |
| **User** | EMS / 911 operations supervisor reviewing borough performance |

---

## Quick start

Python **3.12**, from the repo root:

```bash
pip install -r app/requirements.txt
pytest tests
./app/testme.sh          # Windows: .\app\testme.ps1
```

- Dashboard: http://localhost:8000  
- API docs: http://localhost:8000/docs  
- CLI example: `python app/cli.py --scenario delay --borough Queens --breakdown`

---

## Demo (judges)

Follow **[`demo/README.md`](demo/README.md)** on the **live Connect URL** above: three built-in
scenarios (**Stable Operations**, **High Delay**, **No Delay**), time windows, and borough
drill-down with I-MR and Cpk.

---

## Documentation map

| File | Contents |
|------|----------|
| [`SPEC.md`](SPEC.md) | Method, inputs, outputs, known-answer checks |
| [`docs/proposal.md`](docs/proposal.md) | Product rationale and decisions log |
| [`data/README.md`](data/README.md) | Codebook for the three test CSVs |
| [`app/README.md`](app/README.md) | FastAPI routes, `qc.py`, CLI, rebuild, deploy |
| [`app/qc.py`](app/qc.py) | Tested statistics (`run_qc`, I-MR, CI, Cpk) |
| [`RM.md`](RM.md) | Build roadmap and CONTRACT mapping |
| [`LR.md`](LR.md) | Literature review and SIPOC |

---

## Inputs (summary)

One row per incident. **Required:** borough (`zone` or `borough`), and either `response_time_min` or
both `call_received` and `on_scene_time`. **Optional:** `traffic_level`, `available_units`,
`priority`. See `SPEC.md` §3 and `data/README.md`.

**API:** `POST /api/qc` with `{"response_times_min": [6, 8, 7, 9, 10]}` returns the full `run_qc`
report (same numbers as `pytest`).

---

## Test data

| File | Scenario |
|------|----------|
| `data/stable_operations_2026_24000_synthetic.csv` | Stable Operations |
| `data/highDelayAlex_2026_24000_synthetic.csv` | High Delay |
| `data/noDelayAlexData_2026_24000_synthetic.csv` | No Delay |

---

## Related work (short)

Commercial EMS tools (e.g. FirstWatch) emphasize compliance by zone; this project is a
**transparent teaching tool** with tested **I-MR** and capability in Python. See [`LR.md`](LR.md)
for citations (UGPTI SPC on response times, NFPA 1710 context, percentile reporting).

---

## Known limitation

The dashboard (`app/static/index.html`) computes statistics in **JavaScript** on an embedded
4,800-call sample. **`app/qc.py`**, the CLI, and **`POST /api/qc`** use every row and are what
`pytest` verifies. See `SPEC.md` and `app/README.md`.

---

## Deploy

Pushes to `main` that touch Python, `app/requirements.txt`, or `app/manifest.json` run
[`.github/workflows/deploy-fastapi.yml`](.github/workflows/deploy-fastapi.yml) to Posit Connect
(entrypoint `main:app` in `app/`).

---

## Hackathon event information

This repository started from the [Cornell Six Sigma Hackathon](https://six-sigma-hackathon.devpost.com/)
starter kit. Event schedule, criteria, and templates: [`docs/schedule.md`](docs/schedule.md),
[`docs/criteria.md`](docs/criteria.md), [`docs/start.md`](docs/start.md).

Submit on **Devpost**: repo link + live Connect URL (see [`demo/README.md`](demo/README.md)).
