# Data — codebook

Everything the Chiblings NYC EMS Zone Monitor is demonstrated and tested on lives in this
directory. **All three datasets are simulated. No real incident row is copied, and no file here
came from an ambulance or a hospital.** The shape of every column is what a CAD/EMS dispatch export
looks like, so the same tool would run on a real extract unchanged.

    data/
      noDelayAlexData_2026_24000_synthetic.csv          24,000 rows   (the "clean" year)
      highDelayAlex_2026_24000_synthetic.csv            24,000 rows   (the "slow" year)
      stable_operations_2026_24000_synthetic.csv        24,000 rows   (the "mildly slow" year)
      nyc_normals.py                                    rebuilds app/nyc_normals.json
      README.md                                         this file

`app/nyc_normals.json` (committed, so the tool needs no internet) holds the **real** 12-month NYC
FDNY per-borough response-time normals the tool compares each zone against. `nyc_normals.py` is the
script that downloaded and reduced them from NYC Open Data (`76xm-jjuj`); it needs ~100 MB of
download, so run it only when you want to refresh the normals.

---

## 1. The three datasets

All three cover **2026-01-01 to 2026-12-31** (365 distinct days) for the same five boroughs, and all
three carry a `simulated_special_cause` column that names what the simulator planted. **The tool
never reads that column** — it exists so a reviewer can check that the tool found a problem by
statistics and not by reading the answer key.

| | `noDelayAlexData_…` | `stable_operations_…` | `highDelayAlex_…` |
|---|---|---|---|
| What it is meant to be | a year in which the city is **faster** than normal | a year that is **mildly** slower than normal | a year under a **lasting city-wide delay** |
| median response | 6.55 min | 9.42 min | 18.27 min |
| p90 response | 15.05 min | 22.07 min | 47.08 min |
| p90 at Weekly / Monthly / Yearly | 13.8 / 15.7 / 14.6 min | see §1 note | 44–69 min |
| max response | 39.43 min | 687.55 min | 119.47 min |
| calls < 1 min | 24 | 180 | 2 |
| calls > 120 min | 0 | 120 | 0 |
| traffic High / Medium / Low | 1,403 / 5,896 / 16,701 | 2,922 / 7,444 / 13,634 | 6,184 / 7,265 / 10,551 |
| `available_units` range (median) | 6–10 (8) | 4–8 (7) | 3–8 (6) |
| calls per borough | Bk 6,958 · Mn 5,500 · Bx 5,465 · Qn 4,933 · SI 1,144 | Bk 6,980 · Mn 5,721 · Bx 5,257 · Qn 4,938 · SI 1,104 | Bk 6,958 · Mn 5,500 · Bx 5,465 · Qn 4,933 · SI 1,144 |
| warnings from the tool | none | 120 responses over 120 min kept | none |
| expected status | 🟢 all five in **every** period | 🟢 Daily and Weekly; 🔴 Monthly and Yearly for Bronx, Brooklyn, Manhattan, Queens; Staten Island 🟢 | 🔴 all five from Weekly onward; at Daily, Bronx, Brooklyn and Manhattan 🔴 and Queens, Staten Island still 🟢 |

The borough normals this is compared against are the real NYC p90s: Bronx 21.03, Brooklyn 19.68,
Manhattan 19.23, Queens 22.18, Staten Island 17.47 min. So `noDelayAlexData_…` sits clearly below
every one of them and `highDelayAlex_…` clearly above.

Expected status is **measured, not asserted**: it is what `app/qc.py` reports for the committed
file, and `tests/test_qc.py` fails if it ever changes. The review period always ends at the latest
dispatch in the file, so the windows are identical on every machine.

**Read `stable_operations_…` honestly.** Its name says "stable", but from Monthly onward the run
rule finds a sustained upward shift — 8 consecutive daily medians above the centerline for the
Bronx, 16 for Brooklyn, 8 for Manhattan and 14 for Queens, all starting in early December 2026.
That is the tool doing its job on a real property of the data (winter weather and holiday traffic
are planted in it), not a bug — and it is the clearest demonstration in the pack that the choice of
review period changes the answer.

---

## 2. Columns

| Column | Units / values | Required? | Notes |
|---|---|---|---|
| `incident_id` | text, unique | **required** | 24,000 unique values in every file; a duplicate is dropped with a warning |
| `dispatch_time` | timestamp, local | **required** | when the call was dispatched |
| `on_scene_time` | timestamp, local | **required** | when the unit arrived; a row where this is not after `dispatch_time` is dropped with a warning |
| `zone` | `Bronx`, `Brooklyn`, `Manhattan`, `Queens`, `Staten Island` | **required** | the reporting zone. A non-borough zone is judged against its own first 14 days and says so |
| `call_received` | timestamp, local | optional | kept for reference; not used in any statistic |
| `response_time_min` | minutes | **not read** | present in the two Alex files only; the tool recomputes the interval from the two timestamps (see §3) |
| `borough` | same five names | optional | present in the two Alex files; identical to `zone` in every row. `stable_operations_…` omits it, which is the point: the tool must run without it |
| `traffic_level` | `Low`, `Medium`, `High` | optional | used for the "Traffic HIGH" condition only when a zone is already flagged |
| `available_units` | integer | optional | used for the "Units LOW" condition only |
| `priority` | `Low`, `Medium`, `High` | optional | context only; the tool does **not** chart or threshold on it (the data has no priority effect) |
| `simulated_special_cause` | text | **never read** | the simulator's answer key. The tool must reach the same conclusion from the numbers |

Only the four **required** columns are truly needed. The tool runs, and the statistics stay correct,
with just those four.

---

## 3. What the tool does to the data — and the one number that will not match

1. **It recomputes `response_time_min` from the timestamps** and ignores any column of that name.
   In the two Alex files the provided column disagrees with its own timestamps by up to **2.3
   minutes** (`highDelayAlex_…` states `1.28`–`120.00`; the timestamps give `0.78`–`119.47`). The
   tool's number is the one on screen. This is deliberate: SPEC.md section 3 says the interval is
   derived, never entered — a hand-entered or stale duration column is exactly the kind of error a
   control chart must not inherit.
2. **It drops bad rows with one warning each**: a missing or unreadable dispatch/on-scene time, a
   duplicate `incident_id`, or an on-scene time not after the dispatch time.
3. **It keeps, but flags, implausible long calls.** `stable_operations_…` has 120 calls over 120
   minutes (38 of them over 5 hours, the longest 687.55 min = 11.5 h). Dropping them would hide the
   very tail the p90 test watches, so they are kept and the warning is shown.
4. **It does not repair sub-second calls.** `stable_operations_…` has a 0.02-minute call (1.2
   seconds) and 180 calls under a minute. Those are impossible on-scene times in reality; they are
   the simulator's tail, and the tool leaves them in. If this were real data the honest next step
   would be a documented lower bound — it is listed as a known limitation, not silently fixed.

**No file in this directory contains a deliberately broken row.** The validation behaviour in step 2
is therefore proven by unit tests that build the broken rows in memory
(`tests/test_qc.py::test_bad_rows_are_dropped_with_a_warning_for_each_kind`), not by a demo dataset.

---

## 4. How this data would be collected for real

The tool's input is the EMS CAD (computer-aided dispatch) incident export that every 911 centre
already produces: one row per incident, with the dispatch time, the on-scene time, and the
responding zone. `traffic_level` corresponds to a traffic-feed overlay, `available_units` to the
CAD unit-status table, and `priority` to the call-taking priority code. Real collection would add
the columns this simulation leaves out and that the method cannot do without: a **unit identifier**
(a zone's times mix several units), a **cancellation flag** (a cancelled call has no on-scene time
and must not be counted as a fast response), and **mutual-aid flags** (a borough answering another
borough's call makes both look wrong).

The real normals the tool compares against — `app/nyc_normals.json` — come from NYC Open Data
dataset `76xm-jjuj` (FDNY incident response times), reduced to one 12-month centre/p90 per borough.
That file is real data; the three test CSVs are not.

## 5. Reproducibility

The three CSVs are committed, so a fresh clone reproduces every number in this codebook and every
test result with no download and no seed. Their **generator script is not in this repo** (it was run
once, off-repo, by the teammate who built them); the files themselves are the artifact of record.
Committing the generator is an open item — see `docs/plan.md`, risks.
