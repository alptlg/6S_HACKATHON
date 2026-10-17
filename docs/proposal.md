# Proposal: NYC EMS Zone Monitor (team Chiblings)

Status: **agreed and built.** `SPEC.md`, `RM.md`, `data/README.md` and the code in `app/` follow
this proposal and use the same names for every variable.

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
call-to-dispatch time. When `call_received` is provided, the tool also derives
`call_to_dispatch_min = dispatch_time - call_received` as **context only** (section 6); it never
drives the control chart, p90 or zone status.

## 4. Inputs: plug-and-play CSV

| Column | Required? | Meaning | Real-world source |
|---|---|---|---|
| `incident_id` | **required** | unique id | CAD (Computer-Aided Dispatch) system |
| `dispatch_time` | **required** | unit assigned, `YYYY-MM-DD HH:MM:SS` | CAD timestamp |
| `on_scene_time` | **required** | unit arrived, `YYYY-MM-DD HH:MM:SS` | CAD / crew status button |
| `zone` | **required** | borough / zone name | CAD incident location |
| `call_received` | optional | 911 call received, `YYYY-MM-DD HH:MM:SS` | CAD / phone system timestamp |
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
| `call_to_dispatch_min` | dispatch - call received (only when `call_received` is provided) |
| time of day | Overnight / Morning / Day / Evening peak / Night, from dispatch time |
| day / week / month / year | from dispatch time; drives the review-period filter |
| `recent_call_volume` (workload) | incidents dispatched in the same zone in the previous 15 minutes |
| p90, p95, median, mean | per zone and period |
| control limits, special-cause points, zone status | section 5 |

**Data checks:** both timestamps present; response time > 0; when `call_received` is present,
`call_received <= dispatch_time <= on_scene_time`; duplicate `incident_id` removed; response
times over 60 min kept but marked "check for data-entry error".

## 5. Analysis

1. **Each borough's normal comes from real NYC data.** We downloaded 12 months of FDNY incidents
   (NYC Open Data, *EMS Incident Dispatch Data*, dataset `76xm-jjuj`,
   https://data.cityofnewyork.us/Public-Safety/EMS-Incident-Dispatch-Data/76xm-jjuj),
   Oct 2025 - Sep 2026: 1,461,139 incidents, 1,442,227 kept (FDNY's valid-response-time flag,
   known borough, on scene after assignment, all severities). `data/nyc_normals.py` computes, per
   borough and in dispatch order, the statistics below and stores them in `app/nyc_normals.json`:

   | Borough | Calls | Median | p90 | Center | UCL | Normal share above UCL |
   |---|---|---|---|---|---|---|
   | Bronx | 329,179 | 9.1 min | 21.0 min | 9.4 min | 68.7 min | 1.7% |
   | Brooklyn | 416,731 | 8.7 | 19.7 | 8.8 | 57.9 | 0.8% |
   | Manhattan | 332,295 | 8.3 | 19.2 | 8.5 | 64.1 | 1.3% |
   | Queens | 298,949 | 9.8 | 22.2 | 9.8 | 72.0 | 0.8% |
   | Staten Island | 65,073 | 8.4 | 17.5 | 8.4 | 47.2 | 0.75% |

   **The 8-minute target is dropped:** real dispatch-to-on-scene p90s are 17-22 minutes and
   differ by borough, so every borough is judged against its own normal.
2. **Log I-MR control chart per borough.** Response times are right-skewed, so the chart uses
   `y = ln(response_time_min)`: centerline = mean of `y`, limits = mean +/- 2.66 x average moving
   range; MR chart UCL = 3.267 x average MR, all from the borough's NYC normal. Limits are shown in
   minutes via `exp()`. A zone that is not an NYC borough uses its own first 14 days instead.
3. **Fixed limits.** The Live (last 3 h) / Daily (24 h) / Weekly (7 days) / Monthly (30 days) /
   Yearly (365 days) filter, each ending at the latest call, only changes **which calls are
   checked**; the limits never move, so a bad month cannot hide inside its own wider limits.
4. **Percentiles and bootstrap:** p90, p95, median, mean, and a bootstrap interval for the
   period's p90 (1,000 resamples, fixed seed, at least 20 calls).
5. **Zone status** (applied to the selected period):

| Status | Rule |
|---|---|
| 🔴 Needs Attention | calls above UCL beyond chance AND at least 3 AND at least 3x the borough's normal rate; OR 8 consecutive **daily medians** above the centerline; OR the **99%** bootstrap interval of p90 is entirely above the borough's normal p90 + 5% |
| 🟡 Watch | calls above UCL beyond chance (more than expected + 3 x sqrt(expected), expected = normal rate x calls in the period); OR the **95%** bootstrap interval of p90 is entirely above normal p90 + 5% |
| ⚪ Insufficient data | a non-borough zone with fewer than 20 calls in its first 14 days |
| 🟢 Normal | none of the above |

   *Why "beyond chance" and "3x the normal rate":* even in normal operations 0.75-1.7% of real NYC
   calls land above the UCL (heavier tail than a normal curve), so with thousands of calls a
   month every borough would be flagged by "any call above UCL".
   *Why 99% for Red:* Bonferroni for 5 boroughs, so the chance of a false red anywhere is about 5%.
   *Why +5%:* with thousands of calls, a p90 a few seconds above normal is statistically
   significant but not operationally meaningful (statistical vs practical significance).
   *Why the run rule uses daily medians:* 8 consecutive individual calls above the centerline
   happens by chance about once every 256 calls; 8 consecutive days is a real sustained shift.

**Known-answer checks** (from `SPEC.md`): for [6, 8, 7, 9, 10] min, the log I-MR gives centerline
7.87, UCL 13.21, LCL 4.69 min; MR UCL 0.6353 (log units); p90 = 9.6 min.

## 6. The two kinds of "why"

**A. Statistical reason** (always shown), for example:
- "p90 26.4 min is significantly above the normal 21.0 min (99% bootstrap interval 25.8-27.2)"
- "6 calls above the upper control limit"
- "sustained upward shift: 21 consecutive daily medians above the centerline since 2026-09-09"

**B. Possible operational conditions** (only when the optional columns exist). For the flagged
period, each condition is compared with the zone's baseline:

| Condition | Marked 🔴 when |
|---|---|
| Traffic | share of High-traffic calls is clearly above the baseline share |
| Workload | median recent call volume is above the baseline 75th percentile |
| Unit availability | median available units is below the baseline 25th percentile |
| Call-to-dispatch delay | median `call_to_dispatch_min` is above the baseline 75th percentile (calls waited longer for a unit: supports a resource constraint) |
| Time of day | most long responses fall in one time-of-day period |

and summarized as one pattern:

| Conditions marked 🔴 | Pattern shown |
|---|---|
| traffic only | **Travel conditions** |
| workload only | **High-demand pressure** |
| units and/or call-to-dispatch delay only | **Resource constraint** |
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
P90: 26.4 (normal 21.0)          P90: 20.3 (normal 19.2)  P90: 17.4 (normal 17.5)
Reason: sustained process shift
Possible conditions: Traffic High · Units Low · Workload High · Call-to-dispatch Long
```

**Zone detail (on click):** status and statistical reason, p90 vs baseline, when the shift
started, the I-MR chart with out-of-control calls in red, the conditions vs baseline (including
median call-to-dispatch time when `call_received` exists), and the pattern.

## 8. Test data: simulated from the real NYC distributions

**The test files are generated by `app/simulate.py` with fixed random seeds.** No real incident
row is copied: each borough's response times are **drawn from its real 12-month NYC
distribution** (the 201 stored log-quantiles in `app/nyc_normals.json`), and call volume follows
NYC's real hour-of-day pattern for that borough, scaled to 25% to keep files small. Traffic,
available units, call-to-dispatch gaps and priority are simulated (NYC does not publish them).

**Columns in the generated files:** `incident_id`, `call_received`, `dispatch_time`,
`on_scene_time`, `zone`, `traffic_level`, `available_units`, `priority`, plus the test-only
`simulated_special_cause` (marks where a problem was planted so the tests can check it is found;
the tool never reads it). Derived fields are not stored: the tool computes them.

**Zones:** the 5 NYC boroughs. **Span:** 60 days (2026-08-01 to 2026-09-29). **Volume:** about 985
calls a day across the city (25% of NYC), 2.5x more under a planted demand surge.

**Simulation model:** normal response times come from the real distribution; planted problems
add delay on top:

```
response_time = draw from the borough's NYC distribution
                + traffic_effect + workload_effect + low_unit_effect   (planted periods only)
```

| Part | Value (our assumption, stated in the codebook) |
|---|---|
| traffic | share of High by time of day: Overnight 2%, Morning 15%, Day 8%, Evening peak 20%, Night 5%; planted: 85% High; planted effect Medium +1.5, High +4.0 min |
| workload | planted demand surge 2.5x; +3.0 min when `recent_call_volume` >= 2x the borough's normal 15-minute volume |
| availability | normally 5-8 units; planted 0-2 units, +4.0 min |
| `call_received` | 0.5-2 min before dispatch normally; 3-6 min when 0-2 units are available |
| isolated delays | Manhattan: 60 single calls at 1.3-2.0x the borough's UCL |
| priority | High 30%, Medium 50%, Low 20%; context only |

**Three test files** (problems planted from day 40, 2026-09-09):

| File | What is planted | Expected result |
|---|---|---|
| `stable_operations.csv` (58,744 rows) | nothing | all 🟢 in every period |
| `zone_patterns.csv` (74,927 rows) | **Staten Island** normal · **Queens** high traffic · **Bronx** demand surge + 0-2 units (calls also wait longer before dispatch) · **Brooklyn** all three · **Manhattan** normal conditions but 60 isolated extreme delays | Weekly and Monthly: 🟢 · 🔴 Travel conditions · 🔴 Demand/resource pressure · 🔴 Combined stress · 🟡 Unexplained special cause |
| `minimal_input.csv` (4,123 rows) | **only the 4 required columns**, 21 days, 3 boroughs plus "Harbor Unit" and "Ferry Terminal" (not boroughs; Ferry Terminal has only 3 calls), plus bad rows (2 missing times, 2 on-scene before dispatch, 1 duplicate id) | statistics still work; "factors unavailable"; warnings for bad rows and non-borough zones; Harbor Unit uses its own first 14 days; Ferry Terminal ⚪ Insufficient data; no crash |

`data/README.md` (the codebook) labels every file **simulated**, explains every column, its
units, how it was generated, and how a real dispatch center would collect it.

## 9. Out of scope

Ambulance assignment or dispatch recommendations, managing individual dispatchers, route
optimization, live GPS, hospital selection or offload modelling, ML forecasting, causal inference,
Google Maps or any live API, real 911 integration, automatic operational decisions, logins,
databases.

## 10. Build order

**Must-have (by Sat ~2 AM):** simulator + 3 test files + codebook -> `app/qc.py` (response time,
call-to-dispatch time, log I-MR, percentiles, zone status, statistical reason, conditions vs baseline) with tests -> API
-> zone cards -> zone detail -> period filter.
**If time allows:** incident-logging form (session only, CSV download), polish.

## 11. Changes made in `SPEC.md` (done)

| SPEC section | Change |
|---|---|
| 2. User and use case | Final product purpose and the supervisor's 5 questions (sections 1-2) |
| 3. Inputs | 4 required + 4 optional columns; `on_scene_time`; `call_received` and `priority` optional; derived fields incl. `call_to_dispatch_min` |
| 4. Statistics | Borough normals from 12 months of NYC data; 8-minute target dropped; bootstrap p90 test; 🟢/🟡/🔴 rules relative to each borough; the two kinds of "why" |
| 6. Outputs | Zone cards with normal p90, zone detail, period selector |
| 7. Datasets | The three files in section 8, drawn from the NYC distributions |
| 9. Out of scope | Section 9 |

`RM.md`, `data/README.md` and `app/README.md` were updated the same way.

## 12. Decisions log

- Response time = on scene - dispatch; `call_received` optional (context only).
- Borough normals from 12 months of real NYC data (Oct 2025 - Sep 2026), all valid incidents.
- Control limits from each borough's NYC normal; non-borough zones use their first 14 days.
- Fixed 8-minute target dropped; p90 judged with a bootstrap interval against each borough's
  normal p90 (+5% practical margin; 95% for Watch, 99% for Red).
- Test data drawn from the real borough distributions, problems planted from day 40.
