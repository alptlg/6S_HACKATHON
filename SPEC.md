# SPEC: Six Sigma Hackathon team project

What your tool IS. Your agent reads this before every task. Where the code and this file
disagree, the code is the bug: change this file first, then the code.

Most of this page is already decided by the event and the [rubric](docs/criteria.md).
**Only the `FILL IN` lines change, and you do not have to write them by hand:** describe your app and ask your agent to update them. They depend on the prompt your team picks at kickoff
(prompts are secret until then, see [`docs/prompts.md`](docs/prompts.md)) and on your team.
The examples after each `FILL IN` show the shape of an answer. They are not hints about the prompts.

## 1. Team and prompt
- **Team name:** Chiblings
- **Track:** On-Campus
- **Prompt we chose:** Prompt #2, Health Systems Emergency Response
- **Our public repo:** https://github.com/alptlg/6S_HACKATHON

## 2. User and use case (rubric: scope 5, user and use case 5)
- **User:** The emergency medical services (EMS) dispatch supervisor responsible for monitoring ambulance response times across different city zones.

- **Decision the tool helps them make, and when:** The tool helps the EMS dispatch supervisor identify unusually slow ambulance responses, determine which city zones are experiencing excessive delays, and decide when to investigate dispatch inefficiencies or adjust ambulance resource allocation. The supervisor uses the dashboard throughout the day to monitor incoming incidents and review response-time trends.

- **Why this matches the prompt:** The tool directly addresses the problem of inconsistent ambulance response times across city zones by collecting incident-level data, applying statistical quality control methods, identifying outliers, and flagging zones that require investigation.

## 3. Inputs (rubric: minimal inputs 5)
Only what this user can actually measure or already knows. Fewer is better; every input a user
cannot measure costs points.

The user uploads a CSV file containing ambulance response records. Each row represents one emergency incident. The required information is routinely recorded by emergency dispatch centers, so no specialized equipment or additional measurements are necessary.

| Input | Type and units | Where the user gets it |
|---|---|---|
| `response_data.csv` | CSV file, one row per emergency incident | EMS dispatch records |
| `incident_id` | Unique identifier, integer or string | Automatically assigned by the dispatch system |
| `zone` | Categorical, city zone name | Emergency call location or dispatch records |
| `call_received` | Date and time, YYYY-MM-DD HH:MM:SS | Timestamp recorded when the emergency call is received |
| `dispatch_time` | Date and time, YYYY-MM-DD HH:MM:SS | Timestamp recorded when an ambulance is dispatched |
| `arrival_time` | Date and time, YYYY-MM-DD HH:MM:SS | Timestamp recorded when the ambulance arrives on scene |
| `priority` | Categorical: High, Medium, Low | Emergency classification assigned by the dispatcher |

## 4. The statistics, and why (rubric: valid QC analysis 25)
Say the method in words before any code exists. Load the `stats-first-steering` skill first.
- **Method:** Use an Individuals and Moving Range (I-MR) control chart to monitor ambulance response times in chronological order. Calculate the mean response time, moving ranges, and three-sigma control limits estimated from the average moving range. Additionally, calculate the median, standard deviation, and 90th and 95th percentiles to evaluate response-time performance across city zones. Flag observations outside the control limits and compare response-time distributions between zones.
  - **Response time (decided):** `response_time_min = (arrival_time - dispatch_time)` in minutes, the dispatch-to-on-scene time the prompt names. `call_received` is logged but not charted.
  - **Skewed data (decided):** response times are right-skewed, so the I-MR chart is computed on `ln(response_time_min)`: centerline = mean of the logs, limits = mean +/- 2.66 x average moving range of the logs. Centerline and limits are converted back to minutes with `exp()` for display (the centerline is then the geometric mean).
  - **Zone flag (decided):** a zone is flagged "needs attention" if ANY of its calls is above the upper control limit, OR its 90th-percentile response time is above the 8-minute target (the NFPA 1710 benchmark: 8 minutes for 90% of advanced life support calls). Percentiles use NumPy's default linear method.

- **Why it fits the use case:** I-MR control charts help EMS supervisors identify unusual response-time variation and potential process instability, while percentiles and zone comparisons reveal slow responses that monthly averages may conceal.

- **Assumptions and how the tool checks them:** Response times must be nonnegative, timestamps must be chronologically valid, and incidents must be ordered by call time. Control charts assume a reasonably stable baseline process with comparable observations and limited serial dependence. The tool checks missing values, invalid timestamps, duplicate incidents, chronological ordering, and extreme observations. It displays time-series plots and distributions to assess stability, skewness, and possible changes in operating conditions. Control charts are calculated separately for sufficiently populated zones and comparable priority groups when appropriate. If assumptions are not adequately supported, the tool displays a warning rather than presenting control-limit results as definitive.

- **Known-answer check:** For five chronological response times of [6, 8, 7, 9, 10] minutes, the mean is 8.0 minutes. The consecutive moving ranges are [2, 1, 2, 1], giving an average moving range of 1.5 minutes. Using the standard I-MR chart constant of 2.66, the Individuals chart has a centerline of 8.0 minutes, an upper control limit of 11.99 minutes, and a lower control limit of 4.01 minutes. The Python statistical function must reproduce these values within rounding tolerance.
  - **Log-scale chart (the one the tool uses):** for the same [6, 8, 7, 9, 10] minutes, ln = [1.7918, 2.0794, 1.9459, 2.1972, 2.3026]; mean of logs = 2.0634; moving ranges = [0.2877, 0.1335, 0.2513, 0.1054], average 0.1945. Log limits: UCL = 2.0634 + 2.66 x 0.1945 = 2.5807, LCL = 1.5461. In minutes: centerline 7.87, UCL 13.21, LCL 4.69. Moving Range chart: UCL = 3.267 x 0.1945 = 0.6353 (log units), LCL = 0.
  - **90th percentile:** of [6, 8, 7, 9, 10] = 9.6 minutes, which is above 8, so this zone would be flagged.

Fixed for every team:
- The statistic lives in **one plain, tested function** (`app/qc.py` or `app/qc.R`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

## 5. Delivery (rubric: working tool 25)

- **Stack:** Python REST API using FastAPI, with Pandas and NumPy for statistical analysis and a browser-based dashboard for displaying results. **Dashboard (decided):** FastAPI serves one plain HTML page that draws the charts with Chart.js loaded from a CDN, so no Node.js or React build is needed and the API and page deploy as one app. The application will support CSV uploads, ambulance incident logging, statistical process control analysis, and identification of unusual response times across city zones.

- **Starting demo:** `demos/fastapi/`, copied into `app/`.


Fixed for every team:
- Start from **one** demo in `demos/`, copied to `app/`. Keep its four-script contract
  (`testme`, `manifestme`, `deployme`, `README.md`); `testme` starts the tool with one command.
- Deployed on the course **Posit Connect** server with a public URL (publisher key handed out at the
  event). Deploy early: copy one workflow from
  [`.claude/skills/connect-publish/workflows/`](.claude/skills/connect-publish/workflows/).
- A small tool that runs beats a large tool that does not.

## 6. Outputs

- **What the user sees:** An interactive emergency response monitoring dashboard displaying:

  1. **Response Time Summary:** Mean, median, standard deviation, and 90th and 95th percentile response times, all measured in minutes. Higher values indicate slower ambulance responses.

  2. **Statistical Process Control Charts:** Individuals and Moving Range (I-MR) charts displaying response times over time, with centerlines, upper and lower control limits, and statistically unusual observations highlighted in red. Points beyond control limits indicate potential special-cause variation requiring investigation.

  3. **City Zone Comparison:** Bar charts comparing response-time statistics across city zones to help identify areas experiencing consistently longer delays.

  4. **Zone Alerts:** A list of zones showing statistically unusual response-time behavior, with warning indicators identifying areas that require further investigation. A zone is flagged by the rule in section 4 (a call above the UCL, or 90th percentile above 8 minutes), and the alert says which of the two triggered it.

  5. **Incident Logging:** A form allowing dispatchers to enter new emergency incidents, with response times automatically calculated from timestamps.

  6. **Data Upload:** An interface allowing users to upload CSV files containing historical ambulance response records for analysis.

  7. **Operational Interpretation:** Brief explanations accompanying each statistical result to help EMS supervisors understand what the numbers mean and when further investigation is appropriate.


## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)

2-3 small CSVs in `data/`, invented but shaped like real field data, each showing one behavior.

`data/README.md` is the codebook: every file, every column with units, and what it would take to collect this data for real.

- **Datasets:**
  1. `normal_operations.csv` - Simulated ambulance incidents with stable response times and no intentionally introduced process changes. Used to demonstrate normal operations and establish baseline control limits.

  2. `high_delay_operations.csv` - Simulated ambulance incidents where the South and West zones experience sustained increases in response times. Used to test whether the dashboard identifies persistent response-time problems in specific geographic areas.

  3. `mixed_operations.csv` - Simulated ambulance incidents containing occasional extreme delays and unusual response times. Used to verify that the statistical analysis detects potential special-cause variation and flags incidents requiring investigation.

Each dataset will contain incident IDs, city zones, emergency priority levels, call timestamps, dispatch timestamps, and arrival timestamps.

A separate `data/README.md` codebook will explain every variable, its units, how the synthetic data was generated, and how an EMS center could collect the equivalent information in practice.

## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)
- `README.md` says what the tool does, for whom, every input and parameter, how to run it in one
  command, and walks through the demo on each test dataset.
- Public GitHub repo; a fresh clone runs `testme` and the tests pass with no extra steps.
- Submit on Devpost: the repo link plus a demo.

## 9. Out of scope

What we will NOT build, so nobody (human or agent) builds it by accident.

- Default: logins, databases, real customer data, a second statistic before the first one is tested.

- **Additional exclusions:**
  - No integration with real 911 emergency dispatch systems.
  - No use of actual patient information or confidential medical records.
  - No GPS tracking or live ambulance location monitoring.
  - No automated ambulance dispatching or vehicle assignment.
  - No predictive modeling of future emergency incidents.
  - No optimization algorithm for ambulance routing or resource allocation.
  - No integration with external traffic or mapping services.
  - No automated operational decisions without human review.

The project focuses on collecting incident-level response-time data, performing statistically valid quality control analysis, visualizing response-time variation, and identifying city zones that may require investigation.
