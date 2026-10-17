# SPEC: Six Sigma Hackathon team project

What your tool IS. Your agent reads this before every task. Where the code and this file
disagree, the code is the bug: change this file first, then the code.

Most of this page is already decided by the event and the [rubric](docs/criteria.md).
**Only the `FILL IN` lines change, and you do not have to write them by hand:** describe your app and ask your agent to update them. They depend on the prompt your team picks at kickoff
(prompts are secret until then, see [`docs/prompts.md`](docs/prompts.md)) and on your team.
The examples after each `FILL IN` show the shape of an answer. They are not hints about the prompts.

Full product reasoning: [`docs/proposal.md`](docs/proposal.md). This file and the proposal use the
same names for every variable.

## 1. Team and prompt
- **Team name:** Chiblings
- **Track:** On-Campus
- **Prompt we chose:** Prompt #2, Health Systems Emergency Response
- **Our public repo:** https://github.com/alptlg/6S_HACKATHON

## 2. User and use case (rubric: scope 5, user and use case 5)
- **User:** The EMS / 911 operations supervisor who monitors ambulance response times across
  the city's zones (the 5 NYC boroughs in our demo).

- **Decision the tool helps them make, and when:** During a shift (Live view) and in periodic
  reviews (Daily / Weekly / Monthly / Yearly), the supervisor sees which zones are normal, which
  need attention, whether a problem is one unusually late ambulance or a sustained process shift,
  when it started, and which operating conditions (traffic, workload, unit availability,
  call-to-dispatch delay) coincided with it, so they know where to investigate. The tool never
  assigns ambulances and does not manage individual dispatchers.

- **Why this matches the prompt:** The prompt says dispatch-to-on-scene times vary widely across
  zones while the 911 center only looks at monthly averages. Our tool monitors exactly that
  interval per zone with statistical process control and percentiles, so outliers and shifts
  that averages hide are flagged, with the zone and the conditions present.

## 3. Inputs (rubric: minimal inputs 5)
Only what this user can actually measure or already knows. Fewer is better; every input a user
cannot measure costs points.

The user uploads a CSV with one row per EMS incident. **Only 4 columns are required**; all of them
are recorded automatically by a dispatch center's CAD (Computer-Aided Dispatch) system.

| Input | Required? | Type and units | Where the user gets it |
|---|---|---|---|
| `incident_id` | required | text, unique per incident | CAD incident number |
| `dispatch_time` | required | date-time `YYYY-MM-DD HH:MM:SS` | CAD: unit assigned |
| `on_scene_time` | required | date-time `YYYY-MM-DD HH:MM:SS` | CAD / crew "on scene" button |
| `zone` | required | text (borough name) | CAD incident location |
| `call_received` | optional | date-time `YYYY-MM-DD HH:MM:SS` | CAD / phone system: 911 call answered |
| `traffic_level` | optional | Low / Medium / High | dispatcher entry or a traffic feed |
| `available_units` | optional | integer, free ambulances in the zone at dispatch | CAD unit-status board |
| `priority` | optional | High / Medium / Low | dispatcher triage |

Derived by the tool (never entered): `response_time_min`, `call_to_dispatch_min`, `time_of_day`
(Overnight 0-5, Morning 6-9, Day 10-15, Evening peak 16-19, Night 20-23), `recent_call_volume`
(calls dispatched in the same zone in the previous 15 minutes), percentiles, control limits,
zone status. Without the optional columns the full statistics still run and the tool says
"Operational contributing factors are unavailable in the uploaded data".

## 4. The statistics, and why (rubric: valid QC analysis 25)
Say the method in words before any code exists. Load the `stats-first-steering` skill first.
- **Method:** `response_time_min = on_scene_time - dispatch_time` (minutes). Each zone gets an
  Individuals and Moving Range (I-MR) control chart on `ln(response_time_min)`, in dispatch order.
  **Each NYC borough's normal comes from real data:** 12 months of FDNY incidents (NYC Open Data,
  *EMS Incident Dispatch Data*, dataset `76xm-jjuj`, Oct 2025 - Sep 2026, 1,442,227 valid
  incidents; built by `data/nyc_normals.py`, stored in `app/nyc_normals.json`). From each
  borough's calls in dispatch order: centerline = mean of the logs; UCL/LCL = centerline +/- 2.66
  x average moving range; MR chart UCL = 3.267 x average moving range; normal p90; and the share
  of normal calls above the UCL. Limits are shown in minutes with `exp()` and never move with the
  review period. A zone that is not an NYC borough uses its own first 14 days instead. For the
  chosen period (Live = last 3 h, Daily = 24 h, Weekly = 7 days, Monthly = 30 days, Yearly = 365
  days, all ending at the latest call) the tool reports median, mean, SD, p90, p95, calls above
  the UCL, a run rule on daily medians and a bootstrap interval for p90, and sets the status:

  | Status | Rule (first match wins) |
  |---|---|
  | 🔴 Needs attention | calls above the UCL are beyond chance AND at least 3 AND at least 3x the borough's normal rate; OR 8 consecutive daily medians above the centerline (sustained shift); OR the 99% bootstrap interval of the period's p90 lies entirely above the borough's normal p90 + 5% |
  | 🟡 Watch | calls above the UCL beyond chance (more than expected + 3 x sqrt(expected), expected = normal rate x calls in the period, at least 0.135%); OR the 95% bootstrap interval of p90 lies entirely above normal p90 + 5% |
  | 🟢 Normal | none of the above |
  | ⚪ Insufficient data | a non-borough zone with fewer than 20 calls in its first 14 days |

  Bootstrap: 1,000 resamples with a fixed seed; the p90 test needs at least 20 calls in the
  period. 99% for Red is Bonferroni for 5 boroughs (familywise 95%). The +5% is a practical
  margin: with thousands of calls, a p90 a few seconds above normal is "significant" but does not
  matter operationally.

  For a flagged zone, the period's conditions are compared with the data's own first 14 days (the
  NYC data has no traffic or unit counts): Workload HIGH if median `recent_call_volume` > that
  baseline's 75th percentile; Traffic HIGH if the share of High-traffic calls >= baseline share +
  15 points; Units LOW if median `available_units` < baseline 25th percentile; Call-to-dispatch
  LONG if median `call_to_dispatch_min` > baseline 75th percentile. The pattern is Travel
  conditions (traffic), High-demand pressure (workload), Resource constraint (units and/or
  call-to-dispatch), Demand / resource pressure (workload + resource), Combined operational stress
  (traffic + workload or resource), or Unexplained special cause (abnormal but no condition
  flagged: manual incident review).

- **Two descriptive charts (added 2026-10-17).** These two describe; they never create a status.
  Nothing they compute feeds the rules above, and adding them must leave every zone's status
  unchanged.
  1. **Box plot, by day of week (or by month).** Compares the median, the spread and the unusually
     long calls across periods. Drawn on `ln(response_time_min)`, because on raw minutes Tukey's
     upper fence falls inside the long right tail and nearly every long call would look like an
     outlier; the axis is labelled in minutes (`exp` of the log values). Quartiles use linear
     interpolation (type 7, the NumPy default; R's `boxplot` and Excel's `QUARTILE.INC` agree).
     The fences are Tukey's, `Q1 - 1.5*IQR` and `Q3 + 1.5*IQR`, computed **on the log scale**; a
     call is an outlier only beyond a fence. Whiskers reach the most extreme call inside the
     fences. A box needs at least 5 calls, and a period that yields one box is reported as "not a
     comparison" instead of being drawn.
  2. **Weekday x hour heatmap.** One cell per weekday and hour (7 x 24 = 168) for one zone in the
     chosen period. The cell value is the **p90** in minutes, never the mean: with a right-skewed
     distribution one 60-minute call moves a mean and does not move a p90. A cell with fewer than
     20 calls reads "not enough calls" and is left uncoloured, never 0 and never a number, because
     an empty cell means "no evidence", not "fast". The hour axis uses the same `time_of_day` bins
     as the rest of the tool, and the cells are built from the same cleaned rows as everything
     else, so the cell counts add up to the calls in the period.

- **Why it fits the use case:** The I-MR chart separates one unusually long response (a single
  point above the limit: Watch at most) from a borough whose whole process has shifted (many
  points above the limit, a run of high days, or a significantly higher p90: Needs attention).
  Comparing each borough with its own real 12-month normal replaces a one-size-fits-all target:
  real NYC p90s are 17-22 minutes and differ by borough.

- **Assumptions and how the tool checks them:** Response times are positive and right-skewed, so
  the chart uses the log; after the log the data is still heavier-tailed than normal (0.75-1.7% of
  real NYC calls are above the UCL instead of 0.135%), so "expected by chance" uses each
  borough's real rate. The last 12 months are assumed to describe normal operations, including
  seasons. Calls are treated as independent; workload surges can cluster long responses, which the
  run rule and the conditions panel make visible. Validation drops rows with missing or unreadable
  times, duplicate `incident_id`, or `on_scene_time` not after `dispatch_time`, and warns about
  each; `call_received` after `dispatch_time` is ignored with a warning; responses over 120 minutes
  are kept and flagged for review. Wording is always "associated with / coincided with", never
  "caused".

- **Known-answer check:** For five chronological response times of [6, 8, 7, 9, 10] minutes, the
  mean is 8.0 minutes. The consecutive moving ranges are [2, 1, 2, 1], giving an average moving
  range of 1.5 minutes. Using the standard I-MR chart constant of 2.66, the Individuals chart has
  a centerline of 8.0 minutes, an upper control limit of 11.99 minutes, and a lower control limit
  of 4.01 minutes. The Python statistical function must reproduce these values within rounding
  tolerance.
  - **Log-scale chart (the one the tool uses):** ln = [1.7918, 2.0794, 1.9459, 2.1972, 2.3026];
    mean of logs = 2.0634; moving ranges = [0.2877, 0.1335, 0.2513, 0.1054], average 0.1945.
    UCL = 2.0634 + 2.66 x 0.1945 = 2.5807, LCL = 1.5461. In minutes: centerline 7.87, UCL 13.21,
    LCL 4.69. Moving Range chart: UCL = 3.267 x 0.1945 = 0.6353 (log units), LCL = 0.
  - **90th percentile:** of [6, 8, 7, 9, 10] = 9.6 minutes (linear interpolation).
  - **Response time from timestamps:** dispatch 17:42:10, on scene 17:51:55 -> 9.75 minutes.
  - **Workload:** calls at 10:00, 10:05, 10:14, 10:20 in one zone -> `recent_call_volume`
    = 0, 1, 2, 2 (the 10:00 call is 20 minutes before 10:20).
  - **Box plot (by day of week or month):** the sorted calls [6, 7, 8, 9, 40] give, in minutes,
    Q1 = 7.0, median = 8.0 and Q3 = 9.0 by linear interpolation. The chart's fences are the
    **log-scale** ones: ln Q1 = 1.945910, ln median = 2.079442, ln Q3 = 2.197225, IQR = 0.251315,
    so the upper fence is 2.197225 + 1.5 x 0.251315 = 2.574197 -> exp = 13.12 minutes (within
    0.1 minutes of the log I-MR UCL of 13.21 above, which is the cross-check that the two agree)
    and the lower fence is 1.945910 - 0.376972 = 1.568938 -> exp = 4.80 minutes. The whiskers end
    at 6.0 and 9.0, and 40 is exactly one outlier. For the five known-answer calls
    [6, 8, 7, 9, 10] the same log-scale fences are 4.80 and 13.12 minutes, there are **zero**
    outliers, and the whiskers end at 6.0 and 10.0. (On raw minutes the fences would be 4.0 and
    12.0; the chart uses the log scale for the reason in the method above, and the raw numbers
    are not what the chart shows.)
  - **Heatmap cell p90:** four calls in one zone, all on a Monday, at 10:05 -> 8 min,
    10:25 -> 6 min, 10:45 -> 10 min and 11:10 -> 7 min. The (Monday, 10) cell holds [6, 8, 10],
    so its p90 is 8 + 0.8 x (10 - 8) = 9.6 minutes, the same interpolation as the p90 bullet
    above. The (Monday, 11) cell holds one call: with a minimum of 1 it reports 7.0 minutes, and
    at the default minimum of 20 it reports "not enough calls" (not 7, not 0). The 168 cell
    counts sum to the 4 calls. One real limit to say out loud: 168 cells need about 20 calls each,
    so one zone fills its grid at **Yearly**; at Monthly most cells read "not enough calls" and at
    Weekly and below almost all of them do. The page says so instead of drawing noise, and the
    demo reads the heatmap at Yearly.

Fixed for every team:
- The statistic lives in **one plain, tested function** (`app/qc.py` or `app/qc.R`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

## 5. Delivery (rubric: working tool 25)

- **Stack:** Python REST API using FastAPI, with Pandas and NumPy for the statistics. **Dashboard:**
  FastAPI serves one plain HTML page that draws the charts with Chart.js loaded from a CDN, so no
  Node.js or React build is needed and the API and page deploy as one app.

- **Starting demo:** `demos/fastapi/`, copied into `app/`.

Fixed for every team:
- Start from **one** demo in `demos/`, copied to `app/`. Keep its four-script contract
  (`testme`, `manifestme`, `deployme`, `README.md`); `testme` starts the tool with one command.
- Deployed on the course **Posit Connect** server with a public URL (publisher key handed out at the
  event). Deploy early: copy one workflow from
  [`.claude/skills/connect-publish/workflows/`](.claude/skills/connect-publish/workflows/).
- A small tool that runs beats a large tool that does not.

## 6. Outputs

- **What the user sees:** a zone-first dashboard.
  1. **Header and controls:** load a sample or upload a CSV; review period
     `[Live | Daily | Weekly | Monthly | Yearly]`.
  2. **Zone cards (one per zone):** status (🟢 Normal / 🟡 Watch / 🔴 Needs attention), p90 in
     minutes next to the borough's normal p90, the main statistical reason, the pattern, and Workload / Traffic / Units /
     Call-to-dispatch as HIGH / LOW / LONG / Normal. How to read it: red means the zone's response
     process is outside its normal behavior in this period, not just one late call.
  3. **Zone detail (click a card):** all statistical reasons, when the shift started, period vs
     normal table (calls, median, p90, p95, limits, calls above UCL vs expected, p90 bootstrap
     intervals), the
     conditions table vs baseline, the pattern, the I-MR chart with calls above the UCL in red,
     and the MR chart.
  4. **Incident logging form:** add one incident; it is kept for the session only and can be
     downloaded as CSV (no database).
  5. **Two descriptive charts in the zone detail** (added 2026-10-17): a box plot of the calls by
     day of week, with a By month toggle, showing the median, the spread and the calls beyond
     Tukey's fences as individual points; and a weekday x hour heatmap of the p90 in minutes for
     that zone and period, with any cell below 20 calls greyed out and labelled "not enough
     calls". The page draws both from the API and computes no percentile itself. Neither chart can
     change a zone's status.
  6. **Removed** on 2026-10-17: the "average response time by priority" charts. `priority` is
     optional context, the test data has no priority effect, and a mean hides exactly what the p90
     in item 3 shows.

## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)

3 CSVs in `data/`, all named `*_synthetic.csv`, 24,000 rows each, all invented and simulated,
all covering 2026-01-01 to 2026-12-31 (364 days) for the same 5 boroughs. No real incident row
is copied; the columns are shaped like a CAD export. `data/README.md` is the codebook: every
file, every column with units, and what it would take to collect this data for real.

The expected result below is not a guess: it is what the tool reports for each file at each
review period, and a teammate can reproduce it in one command (`demo/README.md`). The review
period always ends at the latest dispatch in the file, so the windows are the same every time.

| File | What it is | Expected result |
|---|---|---|
| `noDelayAlexData_2026_24000_synthetic.csv` | a year in which every borough is **faster** than its real NYC normal: the borough normal p90s are 17.47-22.18 min and this file reads 13.8-16.7 min at Weekly, Monthly and Yearly (10.1-19.4 min if you look at single days), and no call is above the control limit | all 5 zones 🟢 Normal in **every** period (⚪ Insufficient data for Staten Island in Live, which has too few calls in 3 hours). The tool must not cry wolf. |
| `highDelayAlex_2026_24000_synthetic.csv` | the same city under a lasting delay (median 18.27 min, p90 47.08 min) with congestion planted | 🔴 Needs attention for all 5 zones from Weekly onward. At Daily, Bronx, Brooklyn and Manhattan are already 🔴 while Queens and Staten Island are still 🟢. Reasons name the borough's own normal rate (Manhattan weekly: 14 calls above the UCL, 11.3% of calls against a normal 1.3%, and a p90 of 68.7 min against the normal 19.2). Pattern: Travel conditions or Unexplained special cause. |
| `stable_operations_2026_24000_synthetic.csv` | a year that is **mildly** worse than normal, with winter weather, holiday traffic and rush-hour causes planted | 🟢 Normal in Daily and Weekly; 🔴 Needs attention at Monthly and Yearly for Bronx, Brooklyn, Manhattan and Queens, with Staten Island 🟢. The reason is the **run rule**: 8, 16, 8 and 14 consecutive daily medians above the borough's centerline (Bronx, Brooklyn, Manhattan, Queens), all starting in early December 2026. Pattern: Unexplained special cause. |

Two honest notes about these files, to keep the demo truthful:

- The third file is named "stable" but it is **not** stable at Monthly and Yearly: the run rule
  catches a sustained mild shift (the run lengths are 8, 16, 8 and 14 days for Bronx, Brooklyn,
  Manhattan and Queens). That is the tool working, not a bug. Say the real reason in the demo
  (`docs/plan.md`, risks).
- The two files with a `response_time_min` column do not agree with their own timestamps (they
  differ by up to 2.3 minutes). The tool **ignores that column and recomputes the interval**
  from `dispatch_time` and `on_scene_time`, so one number in the file and one number on screen
  will differ. The codebook says so. Never "fix" this by reading the column.

None of the three files contains a deliberately broken row. The validation behaviour (a warning
for each missing time, duplicate `incident_id`, or on-scene-before-dispatch) is therefore proven
by `tests/test_qc.py`, not by a demo dataset.


## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)
- `README.md` says what the tool does, for whom, every input and parameter, how to run it in one
  command, and walks through the demo on each test dataset.
- Public GitHub repo; a fresh clone runs `testme` and the tests pass with no extra steps.
- Submit on Devpost: the repo link plus a demo.

## 9. Out of scope
What we will NOT build, so nobody (human or agent) builds it by accident.

- Default: logins, databases, real customer data, a second statistic before the first one is tested.
- Ambulance assignment or dispatch recommendations; managing individual dispatchers.
- Route optimization, live GPS, Google Maps or any live external API.
- Hospital selection or hospital offload modelling.
- Machine-learning forecasting or prediction of future incidents.
- Causal claims about why delays happened (conditions are "associated with", not causes).
- Real 911 integration, real patient data, automatic operational decisions.
