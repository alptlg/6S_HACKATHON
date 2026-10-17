# Data codebook — Chiblings EMS response monitor

**Synthetic data only.** No real patients, addresses, or 911 records. Used for the Cornell Six Sigma Hackathon (Prompt #2).

**Response time (for analysis):** `(arrival_time − dispatch_time)` in **minutes** (`SPEC.md` §4).  
**Chart order:** sort rows by `call_received` before I-MR analysis.

**Regenerate files:** from repo root with `venv_sigma`:

```powershell
python data/generate_datasets.py
```

**Random seed:** `5300` in `generate_datasets.py` (high-delay uses seed+1, mixed uses seed+2 before spikes).

---

## Column reference

| Variable | Unit | Definition & role |
|----------|------|-------------------|
| `incident_id` | ID (text) | Unique emergency incident identifier assigned by the dispatch system. **Role:** primary key. |
| `zone` | category | City response zone (North, South, East, West, Central). **Role:** stratifier for zone comparison and alerts. |
| `priority` | category | Dispatcher urgency: High, Medium, Low. **Role:** covariate (logged for realism; optional filter later). |
| `call_received` | timestamp | When the 911 call was received (`YYYY-MM-DD HH:MM:SS`). **Role:** time order for monitoring; not used in response-time formula. |
| `dispatch_time` | timestamp | When a unit was dispatched. **Role:** start of measured response interval. |
| `arrival_time` | timestamp | When the ambulance arrived on scene. **Role:** end of measured response interval. |

---

## Files

### 1. `normal_operations.csv`

| Item | Detail |
|------|--------|
| **Rows** | 60 |
| **Date span** | Oct 1–22, 2026 (21-day synthetic window) |
| **Story** | Stable operations; all zones drawn from the same log-normal response-time process (~6 min median dispatch-to-arrival). |
| **Expected dashboard** | Control charts mostly in control; zone p90 often near or below **8 min** NFPA-style target; few zone alerts. |

### 2. `high_delay_operations.csv`

| Item | Detail |
|------|--------|
| **Rows** | 60 |
| **Date span** | Oct 1–22, 2026 (same window as normal) |
| **Story** | Same baseline as normal for **North, East, Central**. From **2026-10-12** onward, **South** and **West** use a higher median response time (~11.5 min). |
| **Expected dashboard** | **South** and **West** show higher means and **90th percentiles**; alerts should cite **p90 > 8 min** and/or points above UCL once `app/qc.py` is built. |

### 3. `mixed_operations.csv`

| Item | Detail |
|------|--------|
| **Rows** | 60 |
| **Date span** | Oct 1–22, 2026 |
| **Story** | Baseline similar to normal, plus **six injected slow responses** (16–24.5 min) at fixed row indices after time sort (see `SPIKE_AT_ROWS` / `SPIKE_MINUTES` in `generate_datasets.py`). |
| **Expected dashboard** | A few **individual points** far above typical times; useful for special-cause / OOC interpretation. |

---

## How this would be collected in practice

Dispatchers record times in a **CAD** (Computer-Aided Dispatch) system when a call is received, when a unit is assigned, and when the unit marks on-scene. A supervisor exports a CSV of incidents (IDs, zone, priority, timestamps) for quality review — similar to contract compliance workflows described in `LR.md`.

---

## Validation checklist (Step 1.5)

- [x] No missing required fields  
- [x] Unique `incident_id`  
- [x] `call_received ≤ dispatch_time ≤ arrival_time`  
- [x] Positive dispatch-to-arrival minutes  
- [x] Rows sorted by `call_received` in each file  

---

## Judge quick test

| Question | Answer file |
|----------|-------------|
| Which file shows **normal** baseline? | `normal_operations.csv` |
| Which file shows **zone** sustained delay? | `high_delay_operations.csv` (South & West) |
| Which file shows **occasional extreme** calls? | `mixed_operations.csv` |
