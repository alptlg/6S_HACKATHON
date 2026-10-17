"""Download 12 months of real NYC EMS incidents and compute each borough's "normal" response time.

Source: NYC Open Data, "EMS Incident Dispatch Data" (FDNY), dataset 76xm-jjuj,
https://data.cityofnewyork.us/Public-Safety/EMS-Incident-Dispatch-Data/76xm-jjuj
Window: incidents from 2026-10-01 minus 12 months (2025-10-01) up to 2026-09-30.
Filter: valid_incident_rspns_time_indc = 'Y' (FDNY's own flag for a valid response time) and both
first_assignment_datetime and first_on_scene_datetime present. All severities.

response_time_min = first_on_scene_datetime - first_assignment_datetime   (dispatch to on scene)

Run from the repo root:   python data/nyc_normals.py
Writes app/nyc_normals.json (committed; used by the app) and caches the raw download in
data/nyc_raw/ (gitignored, ~100 MB).
"""

from __future__ import annotations

import io
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "nyc_raw"
OUT = ROOT / "app" / "nyc_normals.json"
API = "https://data.cityofnewyork.us/resource/76xm-jjuj.csv"
SOURCE_URL = "https://data.cityofnewyork.us/Public-Safety/EMS-Incident-Dispatch-Data/76xm-jjuj"
START, END = "2025-10-01T00:00:00", "2026-10-01T00:00:00"
MONTHS = pd.date_range("2025-10-01", "2026-10-01", freq="MS")
PAGE = 50_000
COLUMNS = ["incident_datetime", "first_assignment_datetime", "first_on_scene_datetime",
           "borough", "final_severity_level_code"]
BOROUGHS = {
    "BRONX": "Bronx", "BROOKLYN": "Brooklyn", "MANHATTAN": "Manhattan", "QUEENS": "Queens",
    "RICHMOND / STATEN ISLAND": "Staten Island",
}
I_LIMIT_MULT, MR_UCL_MULT = 2.66, 3.267


def fetch_month(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """One month of valid incidents, paged through the Socrata API (cached on disk)."""
    cache = RAW_DIR / f"ems_{start:%Y_%m}.csv"
    if cache.exists():
        return pd.read_csv(cache)
    where = (f"incident_datetime >= '{start:%Y-%m-%dT%H:%M:%S}' AND "
             f"incident_datetime < '{end:%Y-%m-%dT%H:%M:%S}' AND "
             "valid_incident_rspns_time_indc = 'Y' AND first_assignment_datetime IS NOT NULL "
             "AND first_on_scene_datetime IS NOT NULL")
    parts, offset = [], 0
    while True:
        params = {"$select": ",".join(COLUMNS), "$where": where, "$order": ":id",
                  "$limit": PAGE, "$offset": offset}
        url = API + "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=120) as resp:
                    text = resp.read().decode("utf-8")
                break
            except Exception as err:  # network hiccup: wait and retry
                print(f"  retry {attempt + 1} after error: {err}", flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"could not download {start:%Y-%m} offset {offset}")
        page = pd.read_csv(io.StringIO(text))
        parts.append(page)
        offset += len(page)
        if len(page) < PAGE:
            break
    df = pd.concat(parts, ignore_index=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def borough_normal(df: pd.DataFrame) -> dict:
    """Normal statistics for one borough, calls in dispatch order."""
    df = df.sort_values("first_assignment_datetime")
    rt = df["response_time_min"].to_numpy()
    y = np.log(rt)
    mr_bar = float(np.mean(np.abs(np.diff(y))))
    center = float(np.mean(y))
    ucl, lcl = center + I_LIMIT_MULT * mr_bar, center - I_LIMIT_MULT * mr_bar
    hours = df["first_assignment_datetime"].dt.hour
    days = df["first_assignment_datetime"].dt.normalize().nunique()
    return {
        "n": int(len(rt)),
        "median_min": float(np.median(rt)),
        "mean_min": float(np.mean(rt)),
        "sd_min": float(np.std(rt, ddof=1)),
        "p90_min": float(np.percentile(rt, 90)),
        "p95_min": float(np.percentile(rt, 95)),
        "center_log": center,
        "sd_log": float(np.std(y, ddof=1)),
        "mr_bar_log": mr_bar,
        "ucl_log": ucl,
        "lcl_log": lcl,
        "mr_ucl_log": MR_UCL_MULT * mr_bar,
        "center_min": math.exp(center),
        "ucl_min": math.exp(ucl),
        "lcl_min": math.exp(lcl),
        "rate_above_ucl": float(np.mean(y > ucl)),
        "share_over_60_min": float(np.mean(rt > 60)),
        "calls_per_day": float(len(rt) / days),
        "calls_per_hour_by_hour": [float((hours == h).sum() / days) for h in range(24)],
        "log_quantiles": [float(q) for q in np.quantile(y, np.linspace(0, 1, 201))],
    }


def main() -> None:
    frames = []
    for start, end in zip(MONTHS[:-1], MONTHS[1:]):
        t = time.time()
        month = fetch_month(start, end)
        frames.append(month)
        print(f"{start:%Y-%m}: {len(month):,} rows ({time.time() - t:.0f}s)", flush=True)
    raw = pd.concat(frames, ignore_index=True)
    for col in ("incident_datetime", "first_assignment_datetime", "first_on_scene_datetime"):
        raw[col] = pd.to_datetime(raw[col], errors="coerce")
    raw["zone"] = raw["borough"].map(BOROUGHS)
    raw["response_time_min"] = (
        raw["first_on_scene_datetime"] - raw["first_assignment_datetime"]
    ).dt.total_seconds() / 60
    n_raw = len(raw)
    clean = raw.dropna(subset=["zone", "response_time_min"])
    clean = clean.loc[clean["response_time_min"] > 0]
    print(f"{n_raw:,} downloaded, {len(clean):,} kept (known borough, on scene after dispatch)")

    out = {
        "source": "NYC Open Data, EMS Incident Dispatch Data (FDNY), dataset 76xm-jjuj",
        "source_url": SOURCE_URL,
        "window": {"from": START, "to_exclusive": END},
        "filter": "valid_incident_rspns_time_indc = 'Y'; assignment and on-scene times present; "
                  "known borough; on-scene after assignment; all severities",
        "measure": "response_time_min = first_on_scene_datetime - first_assignment_datetime",
        "rows_downloaded": n_raw,
        "rows_used": int(len(clean)),
        "boroughs": {z: borough_normal(g) for z, g in clean.groupby("zone")},
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    for z, s in out["boroughs"].items():
        print(f"{z:14s} n={s['n']:>7,} median={s['median_min']:.2f} p90={s['p90_min']:.2f} "
              f"center={s['center_min']:.2f} UCL={s['ucl_min']:.2f} sd_log={s['sd_log']:.3f} "
              f"mr_sigma={s['mr_bar_log'] / 1.128:.3f} above_ucl={s['rate_above_ucl']:.4f} "
              f"per_day={s['calls_per_day']:.0f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
