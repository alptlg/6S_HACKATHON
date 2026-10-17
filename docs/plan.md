# Plan: Chiblings NYC EMS Zone Monitor

**The question the tool answers:** which zones' ambulance response times are outside their
normal behaviour in this review period, when did it start, and which conditions came with it.
**Not** "what is the average response time" - a mean hides exactly what SPEC section 4 is for.

**Every statistic, with its formula.** `rt = (on_scene_time - dispatch_time)` in minutes;
`y = ln(rt)`.
- I-MR on the log: `CL = mean(y)`; `MR_i = |y_i - y_(i-1)|`; `MRbar = sum(MR)/(n-1)`;
  `UCL = CL + 2.66*MRbar`; `LCL = CL - 2.66*MRbar` (2.66 = 3/d2, d2 = 1.128 for moving
  ranges of 2); MR chart `UCL = 3.267*MRbar` (D4 for n = 2). Minutes = `exp(log value)`.
- p90: linear interpolation (type 7 / numpy default).
- Bootstrap p90 interval: 1000 resamples, seed 5300, 5th/95th and 0.5th/99.5th quantiles.
- `expected_above_UCL = borough rate above UCL * calls in the period`.
- Status per the SPEC section 4 table (Red / Watch / Green / Insufficient), first match wins.
- Conditions vs the zone's own first 14 days: workload HIGH if median
  `recent_call_volume > baseline p75`; traffic HIGH if share High `>= baseline share + 0.15`;
  units LOW if median `available_units < baseline p25`; call-to-dispatch LONG if median
  `call_to_dispatch_min > baseline p75`. Then the pattern label.
- **New in H-09**, box plot on `ln(rt)`: `Q1, median, Q3` by the same linear interpolation;
  `IQR = Q3 - Q1`; fences `Q1 - 1.5*IQR` and `Q3 + 1.5*IQR` in log units, back to minutes
  with `exp`; whiskers reach the most extreme value inside the fences.
- **New in H-09**, weekday x hour grid: cell `(weekday, hour)` = p90 of `rt` for the calls in
  that cell; `value = None` when the cell has fewer than 20 calls.

## Tasks (CONTRACT ids, in order)

| id | what | owns | known-answer test | degenerate test | est |
|---|---|---|---|---|---|
| H-01 | SPEC.md filled in | SPEC.md | `grep -c "FILL IN[.,]" SPEC.md` = 0 | a teammate says the section 4 method sentence without reading it | 5 min |
| H-02 | test datasets + codebook | data/ | `data/README.md` names every file; each has an expected result | `minimal_input.csv` = 4 required columns only, 5 bad rows | 20 min |
| H-03 | core statistics, one tested function | app/qc.py, app/requirements.txt, tests/ | SPEC section 4: [6,8,7,9,10] -> 8.00, MRbar 1.50, UCL 11.99, LCL 4.01, log UCL 13.21 | constant data raises; n = 1 raises; `[7.0]` gives SD 0, no NaN | 30 min |
| H-04 | FastAPI tool wired to H-03 | app/ (except the H-03 files) | `bash app/testme.sh` then upload a data/ CSV: endpoint numbers == function numbers | `/api/zone` before loading data -> HTTP 400, not a crash | 30 min |
| H-05 | demo on every dataset | demo/, app/frontend/ | each CSV: exact command, the numbers shown, how to read it | must_do on the constant-data file | 25 min |
| H-06 | deploy to Posit Connect | .github/, app/manifest.json | workflow green; public URL answers 200 logged out | URL returns the H-03 numbers for one CSV | 40 min |
| H-07 | README + docs | README.md, app/README.md | fresh clone runs `testme`; tests pass | a teammate who did not write it follows it | 30 min |
| H-08 | public repo + Devpost | .gitignore | `git clone` then testme + tests pass, no extra steps | `git grep -i api_key` finds no real key | 20 min |
| H-09 | day-of-week box plot + weekday x hour p90 heatmap | SPEC.md, app/qc.py, tests/, app/static/ | box on [6,7,8,9,40]: Q1 7.0, med 8.0, Q3 9.0, fences 4.0/12.0, 1 outlier; log fence 13.12 min; heatmap cell p90 = 9.6 min | constant data -> IQR 0, 0 outliers, no inf/inf; one month = one box -> say so, do not draw; empty cell -> None, never 0 | 45 min |

Statistics first (H-03), then the tool (H-04), then the page (H-09). No styling until the
numbers pass review.

## Decisions

1. **Base = commit `24f625f` restored.** Taken as confirmed by "ok go do this" after I
   recommended it; say so if you meant option 2 or 3. The regression commit `68248cc` stayed
   in history, so nothing is lost.
2. **Datasets = the three committed `*_synthetic.csv` files.** Decided by the team on
   2026-10-17 ("you need to use the synthetic data please. Like it says that in the csv file
   name"), which closed the earlier open question. The three CSVs I had restored from `24f625f`
   (`stable_operations.csv`, `zone_patterns.csv`, `minimal_input.csv`) were deleted from the
   working tree — they are still recoverable from `24f625f`. `data/` now holds exactly the three
   files the codebook describes, and `data/README.md` is rewritten to match them. Because no
   dataset carries a deliberately broken row any more, the bad-row validation moved into
   in-memory unit tests. See task H-10.
3. **The API serves those same CSV files.** `/api/samples` used to *regenerate* three samples in
   `app/simulate.py`, so the button named "stable_operations" was not the file named
   `stable_operations_…_synthetic.csv` — two different datasets under one name. `app/main.py` now
   reads the committed CSV, so the button, the codebook and the test all point at one file.
   `app/simulate.py` was deleted on 2026-10-17 once nothing imported it. `app/pack_data.py` is
   still there but dead; see risks.
4. **Deploy H-06 after H-03/H-04 are green**, not before (recommended option, unconfirmed).
5. **No Playwright** (declined by dismissal); the page is verified by HTTP + a teammate's
   eyes.
6. **Plots:** the two average-response-by-priority charts are gone (they were only ever in
   alex's page; the restored `24f625f` page never had them). Added in H-09: the day-of-week box
   plot and the weekday x hour heatmap. Page numbers must come from the API, never from
   JavaScript — the old page computed percentiles and Cpk in JS, which is why it was replaced.
7. **The heatmap is read at Yearly.** Measured, not assumed: with 168 cells and a 20-call
   minimum, one zone fills its grid at Yearly (146 of 168 cells for Bronx) and is *entirely* grey
   at Monthly (0 of 168). The page says so in words rather than drawing 168 grey squares and
   letting someone read it as "all fast". The box plot is the chart that works at short periods,
   because it needs only 5 calls per group.

## Three biggest risks

1. **A teammate overwrites the restore.** The fix is in the working tree only, not committed,
   and `68248cc` is the commit that did the damage last time. Do not commit anything else until
   H-03/H-09/H-10 are in, and never `git add -A`.
2. **The deployed environment differs from this one.** We test on Python 3.14 / pandas 3.0.5 /
   numpy 2.5.2, but `app/requirements.txt` pins pandas 2.3.3 and numpy 2.3.5, and `uvicorn` had
   to be installed by hand. Test on the pinned versions before H-06, or update the pins to the
   versions the tests pass on. This is the most likely cause of a green build with no running
   app.
3. **A number on screen that nobody can reproduce.** The two Alex files carry a
   `response_time_min` column that disagrees with their own timestamps by up to 2.3 minutes, and
   the tool ignores it on purpose (SPEC section 3). A judge comparing the CSV column with the
   dashboard will see a difference; `data/README.md` section 3 explains it and the demo must say
   it out loud. The generator script for the three CSVs is not in the repo, so the files
   themselves are the artifact of record.

Also worth a teammate's decision, neither urgent nor blocking:

- `stable_operations_…_synthetic.csv` is **misnamed**: at Monthly and Yearly the run rule flags
  four of five boroughs. The team kept the name on 2026-10-17 and documents it instead (this file
  and `data/README.md` section 1). The demo must say it out loud.
- `app/pack_data.py` is dead and broken: it imports a `load_csv` that `main.py` does not define
  and writes to a `/tmp/claude-0/...` path from another machine. It is tracked in HEAD, so
  deleting it is a teammate's call. `app/simulate.py` was **deleted** on 2026-10-17 (it
  regenerated the old samples and nothing imported it once `/api/samples` read the CSVs).
