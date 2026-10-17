# Proposal: NYC EMS Response Time Dashboard (team Chiblings)

Status: **built.** `SPEC.md`, `RM.md` and `app/README.md` describe the same tool with the same
names. Where this file and the code disagree, the code is right and this file is out of date.

---

## 1. Product

A **Six Sigma quality dashboard for EMS response times** in the 5 NYC boroughs. For each borough
and time window it answers three questions:

1. **Is the response process stable?** A log-scale I-MR control chart flags calls outside the
   control limits.
2. **What is a typical response, and how sure are we?** The geometric mean with a 95%
   confidence interval.
3. **Can the process meet the NFPA 1710 8-minute target?** One-sided process capability (Cpk).

It also shows which conditions (traffic, unit availability, priority) the out-of-control calls
coincided with. It is **not** an ambulance-assignment tool and does not manage dispatchers.

**Differentiation.** Compliance dashboards ask "was this call later than 8 minutes?". Ours asks
the Six Sigma questions: is the process in control, and is it capable of meeting the target?

## 2. User

**EMS / 911 operations supervisor** reviewing performance by borough. They want to know:

1. Which boroughs meet the 8-minute target, and by how much they miss it?
2. Are there unusual calls (out of control), and what conditions did they coincide with?
3. How does performance change over the last year, 6 months, month, week and day?

## 3. Main measured outcome

```
response_time_min   (from the CSV; otherwise on_scene_time − call_received, in minutes)
```

Call-to-on-scene time, in minutes. Values outside 0–300 minutes are dropped.

## 4. Inputs

| Column | Required? | Meaning |
|---|---|---|
| `borough` or `zone` | **required** | one of the 5 NYC boroughs |
| `response_time_min` | **required** unless both times are given | minutes |
| `call_received`, `on_scene_time` | needed if `response_time_min` is missing | `YYYY-MM-DD HH:MM:SS`; `call_received` also sets the time window |
| `traffic_level` | optional | Low / Medium / High / Gridlock |
| `available_units` | optional | free ambulances at dispatch |
| `priority` | optional | High / Medium / Low |

All of these come from a dispatch center's CAD (Computer-Aided Dispatch) system.

## 5. Analysis (`app/qc.py`)

| Step | Method |
|---|---|
| Control chart | I-MR on `ln(RT)`: CL = mean of logs, limits = CL ± 2.660 × MR̄, MR UCL = 3.267 × MR̄; shown in minutes via `exp()` |
| Confidence interval | 95% t-interval on the mean of logs, back-transformed to the geometric mean; also on the arithmetic mean |
| Capability | `Cpu = (ln 8 − μ_log) / (3 σ_log)`, reported as Cpk; ≥ 1.33 capable, 1.0–1.33 marginal, < 1.0 not capable |
| Descriptive | n, mean, median, SD, p25, p75, p90, min, max, geometric mean; NFPA flag if mean or p90 > 8 min |

*Why the log:* response times are positive and right-skewed. On the log scale the I-MR limits
and Cpk are reasonable under a lognormal assumption, and `exp()` of the mean of logs is the
geometric mean, which is the median of a lognormal distribution.

**Known-answer check** (`tests/test_qc.py`): for [6, 8, 7, 9, 10] min, the log I-MR gives
centerline 7.87, UCL 13.21, LCL 4.69 min; MR UCL 0.6353; geometric-mean 95% CI [6.127, 10.115];
Cpk 0.0265; p90 9.6 min.

## 6. Interface

```
NYC EMERGENCY RESPONSE TIMES
Scenario: [Stable Operations] [High Delay] [No Delay] [Upload Custom CSV]
View:     [Full Year] [Last 6 Mo] [Last 1 Mo] [Last Week] [Last Day]

QUEENS  BROOKLYN  MANHATTAN  BRONX  STATEN ISLAND     (geo mean and p90 per borough)
Avg response by traffic · by unit availability · by priority
```

**Borough page:** map, summary tiles (mean, geo mean, p90, n, Cpk), histogram, I-chart and MR
chart with out-of-control points in red, out-of-control calls by condition, and the 95% CI.

## 7. Test data

Three synthetic files in `data/`, 24,000 calls each over 2026, 5 boroughs. The
`simulated_special_cause` column labels conditions such as rush hour, winter weather and
holiday traffic.

| File | Scenario | Full-year geo mean | p90 | Cpk |
|---|---|---|---|---|
| `stable_operations_2026_24000_synthetic.csv` | Stable Operations | 11.12 min | 23.23 min | −0.18 |
| `highDelayAlex_2026_24000_synthetic.csv` | High Delay | 19.58 | 48.40 | −0.43 |
| `noDelayAlexData_2026_24000_synthetic.csv` | No Delay | 7.71 | 16.30 | 0.02 |

## 8. Out of scope

Ambulance assignment or dispatch recommendations, managing individual dispatchers, route
optimization, live GPS, hospital modelling, ML forecasting, causal claims, live external APIs,
real 911 integration, logins, databases.

## 9. Decisions log

- **Oct 16, first design:** each borough's normal from 12 months of real FDNY data
  (NYC Open Data `76xm-jjuj`), zone status (🟢/🟡/🔴) from out-of-control counts, a run rule and a
  bootstrap p90 test; the 8-minute target was dropped.
- **Oct 17, current design:** the real-data normals, the simulator and the zone-status rules were
  removed. The tool now uses Phase I I-MR limits computed from the data being charted, a CI on
  the geometric mean, and Cpk against the NFPA 1710 8-minute target. The dashboard became one
  self-contained HTML page with three synthetic year-long scenarios.
- **Oct 17:** FastAPI restored as the deployed entrypoint (`main:app`); the command-line report
  moved to `app/cli.py`.
