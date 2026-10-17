# Data codebook — Chiblings NYC EMS Response Time Dashboard

Three **synthetic** test CSVs in this folder. They are **not** real FDNY or patient data: invented
incident-level rows shaped like CAD exports for the five NYC boroughs.

**Main measure:** `response_time_min` — minutes from call received to on-scene (see `SPEC.md` §3–4).
The CLI and dashboard use `on_scene_time − call_received` when `response_time_min` is absent.
Rows outside **0–300 minutes** or with a zone that is not one of the five boroughs are dropped.

**Regenerate full-year CLI numbers** (from repo root, Python 3.12):

```bash
pip install -r app/requirements.txt
python app/cli.py --scenario stable --breakdown
python app/cli.py --scenario delay --breakdown
python app/cli.py --scenario fast --breakdown
```

The live dashboard embeds a stratified sample (4,800 calls per scenario); numbers on Connect may
differ slightly from the CLI, which uses every row. **`app/qc.py`** is the tested reference for
statistics; see `POST /api/qc` in `app/README.md`.

---

## Files and stories

| File | Dashboard scenario | Story |
|------|-------------------|--------|
| `stable_operations_2026_24000_synthetic.csv` | **Stable Operations** | Typical year-long operations; moderate geo mean and p90 |
| `highDelayAlex_2026_24000_synthetic.csv` | **High Delay** | Citywide heavy delays; high geo mean, p90, and poor Cpk |
| `noDelayAlexData_2026_24000_synthetic.csv` | **No Delay** | Faster responses; only scenario whose full-year geo mean is under 8 min |

Each file has **24,000** rows, **2026-01-01** through **2026-12-31**, all five boroughs.

**Full-year totals** (all boroughs combined, from `python app/cli.py --scenario <name>`):

| Scenario | Geo mean (95% CI) | p90 (min) | Cpk (USL = 8 min) |
|----------|-------------------|-----------|-------------------|
| Stable Operations | 11.12 (11.03–11.20) | 23.23 | −0.18 |
| High Delay | 19.58 (19.41–19.76) | 48.40 | −0.43 |
| No Delay | 7.71 (7.66–7.77) | 16.30 | 0.02 |

All three are **not capable** against the NFPA 1710 **8-minute** one-sided target except that No
Delay’s geometric mean sits just below 8 minutes (Cpk ≈ 0.02).

Walkthrough for judges: [`demo/README.md`](../demo/README.md).

---

## Columns

Columns match what a dispatch center could export from CAD. Names are case-insensitive in the CLI.

| Variable | Required for analysis? | Type / values | Role | Real-world source |
|----------|------------------------|---------------|------|-------------------|
| `zone` or `borough` | **yes** | Queens, Brooklyn, Manhattan, Bronx, Staten Island | Borough for charts and filters | CAD incident location |
| `call_received` | **yes** if `response_time_min` missing | `YYYY-MM-DD HH:MM:SS` | Start of measured interval; sets time window | CAD / 911 timestamp |
| `on_scene_time` | **yes** if `response_time_min` missing | `YYYY-MM-DD HH:MM:SS` | End of measured interval | Crew “on scene” in CAD |
| `response_time_min` | optional if both times given | number, minutes | Precomputed response time | CAD report or ETL |
| `dispatch_time` | optional | datetime | Present in files; **not** used for the main interval in the current tool | CAD assignment time |
| `incident_id` | optional | text | Row identifier; not used in statistics | CAD incident number |
| `traffic_level` | optional | Low / Medium / High / Gridlock (Gridlock → High) | Condition charts and OOC attribution | Dispatcher or traffic feed |
| `available_units` | optional | integer | Condition charts | CAD unit-status board |
| `priority` | optional | High / Medium / Low | Condition charts | Dispatcher triage |
| `simulated_special_cause` | test only | text labels (e.g. rush hour, weather) | Documents how rows were generated; **the tool does not read it** | N/A |

**Stable Operations** CSV uses `zone` only (no `borough` or `response_time_min`). **High Delay** and
**No Delay** may include `borough`, `zone`, and `response_time_min` (see `app/cli.py` schema notes).

---

## How the data were generated

Synthetic generators produced year-long call streams with borough labels, timestamps, traffic,
units, priority, and response times tuned to each scenario’s story. The `simulated_special_cause`
column records labels such as `holiday_traffic_new_year` for documentation and grading; it is not
an input to `app/qc.py`.

---

## Collecting this data for real

A supervisor exports one row per incident from CAD: borough, call received, on-scene time (or
response time in minutes), and optional traffic, units, and priority. Cancelled calls and rows
without valid on-scene times should be removed before upload. Upload the same shape through the
dashboard **Upload Custom CSV** or analyze with:

```bash
python app/cli.py --csv data/your_export.csv --borough all --window 1mo
```

---

## Further reading

- Tool specification: [`SPEC.md`](../SPEC.md) §3, §4, §7  
- Product summary: [`docs/proposal.md`](../docs/proposal.md)  
- Statistics implementation: [`app/qc.py`](../app/qc.py), [`app/README.md`](../app/README.md)
