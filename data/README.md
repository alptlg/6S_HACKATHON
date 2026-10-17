# Data codebook: Chiblings NYC EMS Zone Monitor

Two kinds of data are used.

1. **Real reference data (borough normals).** 12 months of FDNY incidents from NYC Open Data,
   *EMS Incident Dispatch Data*, dataset `76xm-jjuj`
   (https://data.cityofnewyork.us/Public-Safety/EMS-Incident-Dispatch-Data/76xm-jjuj),
   incidents from 2025-10-01 to 2026-09-30. `data/nyc_normals.py` downloads it (cached in
   `data/nyc_raw/`, not committed, about 100 MB) and writes the per-borough statistics to
   `app/nyc_normals.json`, which the app uses. 1,461,139 incidents downloaded; 1,442,227 kept.
2. **Simulated test files** (`*.csv` in this folder), made by `app/simulate.py` with fixed seeds.
   No real incident row is copied: response times are **drawn from each borough's real
   distribution**, and traffic, units, call-to-dispatch gaps and priority are simulated. No
   patients, addresses or real call records.

**Rebuild** (from the repo root, with the virtual environment active):

```bash
python data/nyc_normals.py     # real borough normals (about 5 minutes; needs internet)
python -m app.simulate          # the three test files
```

Seeds: `stable_operations` 101, `zone_patterns` 202, `minimal_input` 303. The deployed app
regenerates the same files from these seeds, so the demo needs no upload.

**Main measure:** `response_time_min = on_scene_time - dispatch_time`, in minutes
(`SPEC.md` section 4). The tool computes it; it is not stored in the files.

---

## Real NYC reference data (`app/nyc_normals.json`)

| NYC column | Our use |
|---|---|
| `first_assignment_datetime` | = `dispatch_time` (unit assigned) |
| `first_on_scene_datetime` | = `on_scene_time` |
| `borough` | = `zone` (`RICHMOND / STATEN ISLAND` -> Staten Island) |
| `incident_datetime` | call volume by hour of day |
| `final_severity_level_code` | downloaded for reference; all severities are kept |
| `valid_incident_rspns_time_indc` | only `Y` (FDNY's flag for a valid response time) |

Rows are also dropped if the borough is unknown or the on-scene time is not after assignment.
Stored per borough: number of calls, median, mean, SD, p90, p95 (minutes); log-scale centerline,
average moving range, UCL, LCL and MR UCL (calls in dispatch order); the share of calls above the
UCL; calls per day and per hour of day; 201 quantiles of the log response time (used by the
simulator).

| Borough | Calls | Median | p90 | UCL | Share above UCL |
|---|---|---|---|---|---|
| Bronx | 329,179 | 9.1 min | 21.0 min | 68.7 min | 1.7% |
| Brooklyn | 416,731 | 8.7 | 19.7 | 57.9 | 0.8% |
| Manhattan | 332,295 | 8.3 | 19.2 | 64.1 | 1.3% |
| Queens | 298,949 | 9.8 | 22.2 | 72.0 | 0.8% |
| Staten Island | 65,073 | 8.4 | 17.5 | 47.2 | 0.75% |

---

## Columns of the test files

| Variable | Required by the tool? | Unit / values | Definition and role | How a real dispatch center collects it |
|---|---|---|---|---|
| `incident_id` | required | text, e.g. `EMS-000123` | unique incident id; duplicates are dropped with a warning | assigned by the CAD (Computer-Aided Dispatch) system |
| `call_received` | optional | `YYYY-MM-DD HH:MM:SS` | 911 call answered; gives `call_to_dispatch_min = dispatch_time - call_received` (context only) | CAD / phone system timestamp |
| `dispatch_time` | required | `YYYY-MM-DD HH:MM:SS` | ambulance assigned; **start** of the measured interval; sets chart order | CAD timestamp when the unit is assigned |
| `on_scene_time` | required | `YYYY-MM-DD HH:MM:SS` | ambulance arrived; **end** of the measured interval | crew presses "on scene" on the mobile terminal |
| `zone` | required | Bronx, Brooklyn, Manhattan, Queens, Staten Island (any other name uses its own first 14 days) | where the incident is; each zone gets its own control chart | CAD incident location |
| `traffic_level` | optional | Low / Medium / High | road conditions at dispatch; possible contributing condition | dispatcher entry or a traffic feed |
| `available_units` | optional | integer, ambulances | free ambulances in the zone at dispatch; possible contributing condition | CAD unit-status board |
| `priority` | optional | High / Medium / Low | triage priority; context and filter only | dispatcher triage |
| `simulated_special_cause` | test files only | none / traffic / demand_resource / combined / isolated_delay | where a problem was planted, so tests can check the tool finds it; **the tool never reads it** | not a real-world field |

**Derived by the tool (not in the files):** `response_time_min`; `call_to_dispatch_min`;
`time_of_day` (Overnight 0-5, Morning 6-9, Day 10-15, Evening peak 16-19, Night 20-23);
`recent_call_volume` (calls dispatched in the same zone during the previous 15 minutes).

---

## How the test files are simulated

```
response_time = draw from the borough's real NYC distribution
                + traffic_effect + workload_effect + low_unit_effect   (planted periods only)
```

| Part | Value (our assumption) |
|---|---|
| normal response time | inverse-CDF draw from the borough's 201 real log-quantiles |
| calls per hour | the borough's real NYC calls per hour of day x 25% |
| traffic | share of High: Overnight 2%, Morning 15%, Day 8%, Evening peak 20%, Night 5%; planted 85%; planted effect Medium +1.5, High +4.0 min |
| workload | planted 2.5x call volume; +3.0 min when `recent_call_volume` >= 2x the borough's normal 15-minute volume |
| available units | normally 5-8; planted 0-2, +4.0 min |
| call-to-dispatch gap | 0.5-2 min normally; 3-6 min when 0-2 units are available |
| isolated delays | Manhattan: 60 single calls at 1.3-2.0x its UCL |
| priority | High 30%, Medium 50%, Low 20%; no effect on time |

---

## Files

### 1. `stable_operations.csv`

| Item | Detail |
|---|---|
| Rows | 58,744 |
| Dates | 2026-08-01 to 2026-09-29 (60 days), 5 boroughs |
| Planted | nothing |
| Expected | all zones 🟢 Normal in every period (p90 close to each borough's normal) |

### 2. `zone_patterns.csv`

| Item | Detail |
|---|---|
| Rows | 74,927 |
| Dates | 2026-08-01 to 2026-09-29 (60 days), 5 boroughs |
| Planted (from day 40, 2026-09-09) | **Staten Island** nothing · **Queens** 85% of calls in High traffic · **Bronx** 2.5x call volume and 0-2 units · **Brooklyn** all three · **Manhattan** normal conditions but 60 isolated extreme delays |
| Expected (Weekly and Monthly) | Staten Island 🟢 · Queens 🔴 Travel conditions · Bronx 🔴 Demand / resource pressure · Brooklyn 🔴 Combined operational stress · Manhattan 🟡 Unexplained special cause; shifts start on 2026-09-09 |

### 3. `minimal_input.csv`

| Item | Detail |
|---|---|
| Rows | 4,123 |
| Dates | 2026-08-01 to 2026-08-21 (21 days); Bronx, Brooklyn, Queens and "Harbor Unit" at 5% of NYC volume, plus 3 "Ferry Terminal" calls |
| Columns | **only the 4 required columns** |
| Planted data problems | 2 missing `on_scene_time`, 2 `on_scene_time` before `dispatch_time`, 1 duplicate `incident_id`; two zones that are not NYC boroughs |
| Expected | a warning for each kind of bad row and each non-borough zone; Harbor Unit judged against its own first 14 days; Ferry Terminal ⚪ Insufficient data; other zones 🟢; "Operational contributing factors are unavailable in the uploaded data"; no crash |

---

## Collecting this data for real

Every required column is already recorded by a dispatch center's CAD system: the incident
number, the zone, the time a unit is assigned and the time the crew marks "on scene" (exactly
the fields FDNY publishes as `first_assignment_datetime` and `first_on_scene_datetime`). A
supervisor exports these as a CSV (one row per incident) and uploads it. `call_received` and
`available_units` also come from CAD; `traffic_level` needs a dispatcher entry or a traffic feed.
Real exports should drop cancelled calls and calls without an on-scene time before analysis.
