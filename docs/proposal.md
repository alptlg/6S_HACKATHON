# Proposal: NYC EMS Zone Monitor (team Chiblings)

Status: **final scope, for team review**. `SPEC.md` has NOT been changed yet. Once the team
agrees, the changes in section 11 are made to `SPEC.md`, then `docs/plan.md` is written.

---

## 1. Product

A **statistical EMS operations monitoring tool** that:

- tracks ambulance **dispatch-to-on-scene** response times;
- identifies abnormal response-time behavior: **isolated outliers** and **sustained shifts**;
- flags zones needing attention (🟢 Normal / 🟡 Watch / 🔴 Needs Attention);
- explains **why** a zone was flagged, statistically;
- shows **possible operational conditions** associated with the delay, when that data exists;
- supports **Live / Daily / Weekly / Monthly / Yearly** review.

It is **not** an ambulance-assignment tool and does **not** manage individual dispatchers. The
measured interval starts after dispatch, so the relevant explanations are traffic, workload, unit
availability, geography and time, not call-taking or assignment speed.

**One-line description:** a statistical EMS operations monitoring tool that tracks ambulance
dispatch-to-on-scene response times, detects abnormal outliers and process shifts, flags zones
needing attention, and highlights possible operational conditions associated with deterioration.
It supports live monitoring and daily, weekly, monthly and yearly review, and stays plug-and-play
with a minimal incident-level dataset.

**Differentiation.** Commercial EMS dashboards (for example FirstWatch) already check compliance:
*"was this call later than 8 minutes?"* Ours asks the Six Sigma question: *"has this zone's
response process become abnormal?"* It separates **one unusually long response** from **a zone
whose whole process is becoming unstable**.

## 2. User

**EMS / 911 operations supervisor.** They want to know quickly:

1. Which zones are performing normally?
2. Which zones need attention?
3. Is it an isolated outlier or a sustained shift?
4. What conditions may be associated with the deterioration?
5. How has performance changed over different time periods?

## 3. Main measured outcome

```
response_time_min = (on_scene_time - dispatch_time) in minutes
```

Used everywhere: SPC, percentiles and zone comparison. Turnout plus travel time; it excludes the
call-to-dispatch time.

## 4. Inputs: plug-and-play CSV

| Column | Required? | Meaning | Real-world source |
|---|---|---|---|
| `incident_id` | **required** | unique id | CAD (Computer-Aided Dispatch) system |
| `dispatch_time` | **required** | unit assigned, `YYYY-MM-DD HH:MM:SS` | CAD timestamp |
| `on_scene_time` | **required** | unit arrived, `YYYY-MM-DD HH:MM:SS` | CAD / crew status button |
| `zone` | **required** | borough / zone name | CAD incident location |
| `traffic_level` | optional | Low / Medium / High | dispatcher entry or a traffic feed |
| `available_units` | optional | free ambulances in the zone at dispatch | CAD unit-status board |
| `priority` | optional | High / Medium / Low | dispatcher triage |

**The 4 required columns are enough for the full statistical analysis.** The optional columns only
add the "possible conditions" part. If they are missing, the tool says *"Operational contributing
factors are unavailable in the uploaded data"* and everything else still works.

**Derived automatically** (the user never enters these):

| Derived | How |
|---|---|
| `response_time_min` | on scene - dispatch |
| time of day | Overnight / Morning / Day / Evening peak / Night, from dispatch time |
| day / week / month / year | from dispatch time; drives the review-period filter |
| `recent_call_volume` (workload) | incidents dispatched in the same zone in the previous 15 minutes |
| p90, p95, median, mean | per zone and period |
| control limits, special-cause points, zone status | section 5 |

**Data checks:** both timestamps present; response time > 0; duplicate `incident_id` removed;
response times over 60 min kept but marked "check for data-entry error".

## 5. Analysis

1. **Log I-MR control chart per zone.** Response times are right-skewed, so the chart uses
   `y = ln(response_time_min)`: centerline = mean of `y`, limits = mean +/- 2.66 x average moving
   range; MR chart UCL = 3.267 x average MR. Limits are shown in minutes via `exp()`.
2. **Fixed baseline.** Limits come from each zone's **first 14 days**, assumed normal. The
   Live / Daily / Weekly / Monthly / Yearly filter only changes **which calls are checked**; the
   limits never move, so a bad month cannot hide inside its own wider limits.
3. **Percentiles:** p90, p95, median, mean; % within target (target is a setting, default 8 min,
   the NFPA 1710 benchmark).
4. **Zone status** (applied to the selected period):

| Status | Rule |
|---|---|
| 🔴 Needs Attention | **sustained** signal: at least 3 calls above UCL AND more than 2% of calls above UCL; OR 8 consecutive calls above the centerline; OR p90 above target |
| 🟡 Watch | at least 1 call above UCL (isolated outlier); OR p90 within 10% below target |
| 🟢 Normal | none of the above |

   *Why not "any call above UCL = red":* a stable process still puts about 1 in 740 calls above
   the UCL (0.135%), so with hundreds of calls every stable zone would turn red.

**Known-answer checks** (from `SPEC.md`): for [6, 8, 7, 9, 10] min, the log I-MR gives centerline
7.87, UCL 13.21, LCL 4.69 min; MR UCL 0.6353 (log units); p90 = 9.6 min.

## 6. The two kinds of "why"

**A. Statistical reason** (always shown), for example:
- "p90 12.1 min, above the 8 min target"
- "6 calls above the upper control limit"
- "sustained upward shift: 8+ consecutive calls above the centerline since 16:45"

**B. Possible operational conditions** (only when the optional columns exist). For the flagged
period, each condition is compared with the zone's baseline:

| Condition | Marked 🔴 when |
|---|---|
| Traffic | share of High-traffic calls is clearly above the baseline share |
| Workload | median recent call volume is above the baseline 75th percentile |
| Unit availability | median available units is below the baseline 25th percentile |
| Time of day | most long responses fall in one time-of-day period |

and summarized as one pattern:

| Conditions marked 🔴 | Pattern shown |
|---|---|
| traffic only | **Travel conditions** |
| workload only | **High-demand pressure** |
| units only | **Resource constraint** |
| workload + units | **Demand / resource pressure** |
| traffic + (workload or units) | **Combined operational stress** |
| none, but response is abnormal | **Unexplained special cause:** manual incident review recommended |
| optional columns missing | "Operational contributing factors are unavailable in the uploaded data" |

Wording is always *"possible contributing conditions"* or *"coincided with"*, never "caused".

## 7. Interface (zone first)

```
NYC EMS ZONE MONITOR
[ Live ] [ Daily ] [ Weekly ] [ Monthly ] [ Yearly ]

BRONX     🔴 NEEDS ATTENTION      QUEENS    🟡 WATCH       BROOKLYN  🟢 NORMAL
P90: 12.1 min                     P90: 9.3 min             P90: 7.8 min
Reason: sustained process shift
Possible conditions: Traffic High · Units Low · Workload High
```

**Zone detail (on click):** status and statistical reason, p90 vs baseline, when the shift
started, the I-MR chart with out-of-control calls in red, the conditions vs baseline, and the
pattern.

## 8. Test data: generated only

**All data is generated by our simulator, `data/simulate.py`, with a fixed random seed.** No real
or live data is used, and no external API (no Google Maps).

**Columns in the generated files:** `incident_id`, `dispatch_time`, `on_scene_time`, `zone`,
`traffic_level`, `available_units`, `priority`, plus the test-only `simulated_special_cause`
(marks where a problem was planted so the tests can check it is found; the tool never reads it).
Derived fields are not stored: the tool computes them.

**Zones:** the 5 NYC boroughs. **Span:** 60 days. **Volume:** about 3 calls per 15 min per borough
normally (about 12 per hour), up to 8 or more under stress. That keeps each file near 85,000 rows
(12 x 24 x 60 x 5).

**Simulation model:** response time is generated **from** the conditions, not independently:

```
response_time = (zone_baseline + traffic_effect + workload_effect + low_unit_effect) x exp(noise)
noise ~ Normal(0, 0.25)   (always positive, right-skewed, matches the log I-MR chart)
```

| Part | Value (our assumption, stated in the codebook) |
|---|---|
| zone baseline (min) | Manhattan 6.0, Brooklyn 6.0, Bronx 6.5, Queens 6.5, Staten Island 7.0 |
| traffic | Low +0, Medium +1.0, High +2.5 min; High more likely at Morning and Evening peak |
| workload | Normal +0, High +1.5 min; follows time of day plus planted surges |
| availability | 5+ units +0, 3-4 units +1.0, 0-2 units +2.0 min |
| priority | context/filter only: no effect on time |

**Three test files:**

| File | What is planted (from day 40) | Expected result |
|---|---|---|
| `stable_operations.csv` | nothing: all boroughs normal | all 🟢 |
| `zone_patterns.csv` | **Staten Island** normal · **Queens** high traffic · **Bronx** high workload + low units · **Brooklyn** traffic + workload + low units · **Manhattan** normal conditions but ~10 extreme delays | 🟢 · 🔴 Travel conditions · 🔴 Demand/resource pressure · 🔴 Combined stress · 🟡 Unexplained special cause |
| `minimal_input.csv` | **only the 4 required columns**, plus a few bad rows (missing time, arrival before dispatch) and one zone with only 3 calls | full statistics still work; "factors unavailable" message; clear warnings for bad rows and too-few-calls; no crash |

`data/README.md` (the codebook) labels every file **simulated** and explains every column, its
units, how it was generated, and how a real dispatch center would collect it.

## 9. Out of scope

Ambulance assignment or dispatch recommendations, managing individual dispatchers, route
optimization, live GPS, hospital selection or offload modelling, ML forecasting, causal inference,
Google Maps or any live API, real 911 integration, automatic operational decisions, logins,
databases.

## 10. Build order

**Must-have (by Sat ~2 AM):** simulator + 3 test files + codebook -> `app/qc.py` (response time,
log I-MR, percentiles, zone status, statistical reason, conditions vs baseline) with tests -> API
-> zone cards -> zone detail -> period filter.
**If time allows:** incident-logging form (session only, CSV download), polish.

## 11. Changes needed in `SPEC.md` (after the team agrees)

| SPEC section | Change |
|---|---|
| 2. User and use case | Final product purpose and the supervisor's 5 questions (sections 1-2) |
| 3. Inputs | 4 required + 3 optional columns; rename to `dispatch_time` / `on_scene_time`; drop `call_received`; `priority` becomes optional; list derived fields (section 4) |
| 4. Statistics | Add the fixed 14-day baseline, the 🟢/🟡/🔴 rules and the two kinds of "why" (sections 5-6) |
| 6. Outputs | Zone cards, zone detail, period selector (section 7) |
| 7. Datasets | The three files in section 8 with their expected results; zones become the 5 NYC boroughs |
| 9. Out of scope | Section 9 |

`RM.md` Step 1 (columns, zones, dataset stories) also needs the same update.

## 12. Open questions for the team

1. Are the 🟢/🟡/🔴 thresholds right (3 calls and 2% above UCL; run of 8; within 10% of target)?
2. Is a 14-day baseline at the start of each file OK?
3. Are the simulation effects (minutes per condition) realistic enough?
