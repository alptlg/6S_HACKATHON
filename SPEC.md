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
- **Our public repo:** https://github.com/alptlg/6s_hackathon

## 2. User and use case (rubric: scope 5, user and use case 5)
- **User:** The EMS / 911 operations supervisor who monitors ambulance response times across
  the 5 NYC boroughs.

- **Decision the tool helps them make, and when:** In periodic reviews (full year, last 6
  months, last month, last week, last day), the supervisor sees for each borough whether
  response times are statistically stable (I-MR chart), where the typical response sits with its
  uncertainty (geometric mean and 95% CI), and whether the process can meet the NFPA 1710
  8-minute target (Cpk). They also see which conditions (traffic, unit availability, priority)
  the out-of-control calls coincided with, so they know where to investigate. The tool never
  assigns ambulances and does not manage individual dispatchers.

- **Why this matches the prompt:** The prompt says response times vary widely across zones
  while the 911 center only looks at monthly averages. The tool applies statistical process
  control and capability per borough, so it flags outliers and shifts that averages hide.

## 3. Inputs (rubric: minimal inputs 5)
Only what this user can actually measure or already knows. Fewer is better; every input a user
cannot measure costs points.

The user picks a built-in scenario or uploads a CSV with one row per EMS incident. Every column
comes from a dispatch center's CAD (Computer-Aided Dispatch) system.

| Input | Required? | Type and units | Where the user gets it |
|---|---|---|---|
| `borough` or `zone` | required | text: Queens, Brooklyn, Manhattan, Bronx, Staten Island | CAD incident location |
| `response_time_min` | required unless both times below are given | number, minutes | CAD report |
| `call_received` | required if `response_time_min` is missing; also used for the time window | date-time `YYYY-MM-DD HH:MM:SS` | CAD / phone system: 911 call answered |
| `on_scene_time` | required if `response_time_min` is missing | date-time `YYYY-MM-DD HH:MM:SS` | CAD / crew "on scene" button |
| `traffic_level` | optional | Low / Medium / High (Gridlock counts as High) | dispatcher entry or a traffic feed |
| `available_units` | optional | integer, free ambulances at dispatch | CAD unit-status board |
| `priority` | optional | High / Medium / Low | dispatcher triage |

Derived by the tool (never entered): response time when not given
(`on_scene_time − call_received`, minutes), day and hour of the call, control limits,
confidence interval and Cpk. Rows with a zone that is not one of the 5 boroughs, or a response
time outside 0–300 minutes, are dropped. `incident_id`, `dispatch_time` and
`simulated_special_cause` may be present but are not read.

## 4. The statistics, and why (rubric: valid QC analysis 25)
Say the method in words before any code exists. Load the `stats-first-steering` skill first.
- **Method:** all statistics are in `app/qc.py`, one function each.
  1. **I-MR control chart on `ln(response_time_min)`** in file order (`compute_imr`):
     centerline = mean of the logs; UCL/LCL = centerline ± 2.660 × average moving range (E₂ = 3/d₂,
     d₂ = 1.128 for n = 2); MR chart UCL = 3.267 × average moving range (D₄), LCL = 0. Limits are
     shown in minutes with `exp()`. Points above the UCL are flagged out of control (high); points
     below the LCL are flagged as unusually fast (check the data).
  2. **95% confidence interval** (`compute_confidence_interval`): a t-interval with n − 1 degrees
     of freedom on the arithmetic mean, and on the mean of the logs, back-transformed to a
     geometric-mean interval.
  3. **Process capability** (`compute_capability`): one-sided
     `Cpu = (ln 8 − μ_log) / (3 σ_log)` against the NFPA 1710 8-minute upper spec limit, reported
     as Cpk. ≥ 1.33 capable, 1.0–1.33 marginally capable, < 1.0 not capable. With zero spread,
     Cpk is +∞ if every call meets 8 minutes and −∞ if every call misses it.
  4. **Descriptive statistics** (`compute_descriptive`): n, mean, median, SD, min, p25, p75, p90
     (linear interpolation), max and geometric mean; NFPA flag if the mean or p90 exceeds 8 minutes.
  5. `run_qc` runs all four and writes the alert and warning messages.

  The dashboard and CLI apply these per borough and per time window (full year, last 6 months,
  last month, last week or last day, counted back from the latest call).

- **Why it fits the use case:** The I-MR chart separates single unusually long responses (points
  above the UCL) from ordinary variation. The CI shows how precisely the typical response time is
  known. Cpk turns "how often do we miss 8 minutes" into one number a supervisor can track.

- **Assumptions and how the tool checks them:** Response times are positive and right-skewed, so
  every statistic uses the log (lognormal assumption); non-positive values are rejected. Calls
  are treated as independent and in time order. The I-MR limits come from the same data being
  charted (Phase I), so a borough whose whole year is slow has wide limits and few points out of
  control: Cpk, not the chart, is what shows that. Cpk on the log scale assumes the logs are
  roughly normal.

- **Known-answer check:** five chronological response times [6, 8, 7, 9, 10] minutes, worked by
  hand in `tests/test_qc.py`:
  - **I-MR (log):** ln = [1.7918, 2.0794, 1.9459, 2.1972, 2.3026]; centerline 2.0634; moving
    ranges [0.2877, 0.1335, 0.2513, 0.1054], average 0.1945; UCL 2.5807, LCL 1.5461. In minutes:
    centerline 7.87, UCL 13.21, LCL 4.69. MR UCL = 3.267 × 0.1945 = 0.6353 (log units).
  - **95% CI:** s(ln) = 0.2018, t(0.975, 4) = 2.7764; geometric mean CI [6.127, 10.115] min;
    arithmetic CI 8 ± 1.963 = [6.037, 9.963] min.
  - **Cpk:** (ln 8 − 2.0634) / (3 × 0.2018) = 0.0265 (not capable).
  - **p90:** 9.6 minutes (linear interpolation); NFPA flag on.
  - **Degenerate cases:** constant [5, 5, 5, 5] gives MR̄ = 0, UCL = LCL = 5 min, Cpk +∞;
    constant [10, 10, 10, 10] gives Cpk −∞; n = 1, an empty list or any value ≤ 0 raises an error
    (HTTP 422 from the API).

Fixed for every team:
- The statistic lives in **one plain, tested function** (`app/qc.py` or `app/qc.R`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

**Known gap:** the dashboard (`app/static/index.html`) still computes these statistics in
JavaScript on a 4,800-call sample instead of calling `POST /api/qc`, which breaks the "no
statistics inside UI code" rule. `app/qc.py` is the tested reference.

## 5. Delivery (rubric: working tool 25)

- **Stack:** Python 3.12 with FastAPI, NumPy and SciPy. `app/main.py` (`main:app`) serves the
  dashboard at `/`, `GET /health` and `POST /api/qc`. The dashboard is one self-contained HTML
  page that draws its charts with Chart.js from a CDN, so no Node.js or React build is needed.
  `app/cli.py` prints the same report in a terminal.

- **Starting demo:** `demos/fastapi/`, copied into `app/`.

Fixed for every team:
- Start from **one** demo in `demos/`, copied to `app/`. Keep its four-script contract
  (`testme`, `manifestme`, `deployme`, `README.md`); `testme` starts the tool with one command.
- Deployed on the course **Posit Connect** server with a public URL (publisher key handed out at the
  event). Deploy early: copy one workflow from
  [`.claude/skills/connect-publish/workflows/`](.claude/skills/connect-publish/workflows/).
- A small tool that runs beats a large tool that does not.

## 6. Outputs

- **What the user sees:** a borough-first dashboard.
  1. **Home:** scenario buttons (Stable Operations, High Delay, No Delay) and Upload Custom CSV;
     time window `[Full Year | Last 6 Mo | Last 1 Mo | Last Week | Last Day]`; one card per
     borough with geometric mean and p90; average response by traffic level, unit availability
     and priority across boroughs.
  2. **Borough page (click a borough):** borough map; summary tiles (mean, geometric mean, p90,
     incidents, Cpk with USL = 8), each rated Good / Fair / Bad; histogram; average response by
     priority and by traffic; the I-chart on ln(RT) with out-of-control points in red and a
     geometric / arithmetic centerline toggle; the MR chart; out-of-control calls broken down by
     condition; overall vs out-of-control average response; the 95% CI on the geometric mean.
  3. **API:** `POST /api/qc` returns the full `run_qc` report as JSON.
  4. **CLI:** `python app/cli.py --scenario stable --breakdown` prints the report and a
     per-borough table.

## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)

2-3 small CSVs in `data/`, invented but shaped like real field data, each showing one behavior.

`data/README.md` is the codebook: every file, every column with units, and what it would take to collect this data for real.

- **Datasets** (synthetic, 24,000 calls each, 2026-01-01 to 2026-12-31, 5 boroughs; the
  `simulated_special_cause` column labels conditions such as rush hour, winter weather and
  holiday traffic). Full-year numbers from `python app/cli.py --scenario <name>`:

  | File | Scenario | Geo mean (95% CI) | p90 | Cpk |
  |---|---|---|---|---|
  | `stable_operations_2026_24000_synthetic.csv` | Stable Operations | 11.12 (11.03–11.20) | 23.23 | −0.18 |
  | `highDelayAlex_2026_24000_synthetic.csv` | High Delay | 19.58 (19.41–19.76) | 48.40 | −0.43 |
  | `noDelayAlexData_2026_24000_synthetic.csv` | No Delay | 7.71 (7.66–7.77) | 16.30 | 0.02 |

  All three scenarios are "not capable" against 8 minutes. No Delay is the only one whose
  geometric mean is under 8 minutes.

## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)
- `README.md` says what the tool does, for whom, every input and parameter, how to run it in one
  command, the live Connect URL, and links `demo/README.md` (walkthrough on each scenario).
- Public GitHub repo; a fresh clone runs `testme` and the tests pass with no extra steps.
- Submit on Devpost: the repo link plus a demo.

## 9. Out of scope
What we will NOT build, so nobody (human or agent) builds it by accident.

- Default: logins, databases, real customer data, a second statistic before the first one is tested.
- Zones other than the 5 NYC boroughs.
- Ambulance assignment or dispatch recommendations; managing individual dispatchers.
- Route optimization, live GPS, Google Maps or any live external API.
- Hospital selection or hospital offload modelling.
- Machine-learning forecasting or prediction of future incidents.
- Causal claims about why delays happened (conditions are "associated with", not causes).
- Real 911 integration, real patient data, automatic operational decisions.
