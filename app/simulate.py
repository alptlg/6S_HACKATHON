"""Generate the three EMS test datasets (fixed random seeds, fully reproducible).

No real incident rows are copied: each borough's response times are DRAWN from its real
12-month NYC distribution (app/nyc_normals.json, from NYC Open Data dataset 76xm-jjuj), and call
volumes follow NYC's hour-of-day pattern scaled to 25%. Operating conditions (traffic, available
units, call-to-dispatch gap, priority) are simulated. Planted problems add delay on top:

    response_time = draw from the borough's NYC distribution
                    + traffic_effect + workload_effect + low_unit_effect     (planted periods only)

Run from the repo root:   python -m app.simulate
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    from app.qc import load_normals, recent_call_volume, time_of_day
except ModuleNotFoundError:  # running inside app/ (Posit Connect)
    from qc import load_normals, recent_call_volume, time_of_day

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
START = pd.Timestamp("2026-08-01 00:00:00")
DAYS = 60
PLANT_FROM_DAY = 40  # problems start on day 40 (day 1 = START)
VOLUME_SCALE = 0.25  # share of real NYC call volume simulated (keeps the files small)
BOROUGHS = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]

P_HIGH_TRAFFIC = {"Overnight": 0.02, "Morning": 0.15, "Day": 0.08, "Evening peak": 0.20, "Night": 0.05}
P_MEDIUM_TRAFFIC = {"Overnight": 0.15, "Morning": 0.40, "Day": 0.35, "Evening peak": 0.45, "Night": 0.25}
PRIORITY_P = {"High": 0.3, "Medium": 0.5, "Low": 0.2}

# extra minutes added in planted periods
TRAFFIC_EFFECT = {"Low": 0.0, "Medium": 1.5, "High": 4.0}
WORKLOAD_EFFECT = 3.0  # when recent_call_volume >= 2 x the zone's normal 15-minute volume
LOW_UNIT_EFFECT = 4.0  # when 0-2 units are available
DEMAND_SURGE = 2.5  # call-volume multiplier in demand patterns

PATTERNS = {
    "Staten Island": "none",
    "Queens": "traffic",
    "Bronx": "demand_resource",
    "Brooklyn": "combined",
    "Manhattan": "isolated_delay",
}
N_ISOLATED_DELAYS = 60  # Manhattan: single calls far above the control limit
ISOLATED_DELAY_X_UCL = (1.3, 2.0)  # each delay = UCL x a factor in this range


def draw_response_times(rng: np.random.Generator, zone: str, n: int) -> np.ndarray:
    """n response times (min) from the borough's real NYC distribution (inverse CDF of its
    201 stored log-quantiles)."""
    q = np.asarray(load_normals()["boroughs"][zone]["log_quantiles"])
    u = rng.uniform(0, 1, n) * (len(q) - 1)
    return np.exp(np.interp(u, np.arange(len(q)), q))


def simulate_zone(rng: np.random.Generator, zone: str, pattern: str, days: int,
                  volume_scale: float = VOLUME_SCALE) -> pd.DataFrame:
    """One zone's incidents. pattern: none / traffic / demand_resource / combined /
    isolated_delay (applied from PLANT_FROM_DAY)."""
    normal = load_normals()["boroughs"][zone]
    per_hour = np.asarray(normal["calls_per_hour_by_hour"]) * volume_scale
    plant_start = START + pd.Timedelta(days=PLANT_FROM_DAY - 1)
    demand = pattern in ("demand_resource", "combined")

    times = []
    for h in range(days * 24):
        hour_start = START + pd.Timedelta(hours=h)
        rate = per_hour[hour_start.hour] * (DEMAND_SURGE if demand and hour_start >= plant_start else 1)
        secs = np.sort(rng.uniform(0, 3600, rng.poisson(rate)))
        times.extend(hour_start + pd.to_timedelta(secs.round(), unit="s"))
    df = pd.DataFrame({"dispatch_time": pd.to_datetime(times)})
    df["zone"] = zone
    df = df.sort_values("dispatch_time").reset_index(drop=True)
    n = len(df)
    planted = (df["dispatch_time"] >= plant_start).to_numpy() & (pattern != "none")

    tod = df["dispatch_time"].dt.hour.map(time_of_day)
    p_high = tod.map(P_HIGH_TRAFFIC).to_numpy()
    p_med = tod.map(P_MEDIUM_TRAFFIC).to_numpy()
    if pattern in ("traffic", "combined"):
        p_high = np.where(planted, 0.85, p_high)
        p_med = np.where(planted, 0.10, p_med)
    u = rng.uniform(size=n)
    traffic = np.where(u < p_high, "High", np.where(u < p_high + p_med, "Medium", "Low"))

    units = rng.integers(5, 9, size=n)  # 5-8 available normally
    if demand:
        units = np.where(planted, rng.integers(0, 3, size=n), units)

    response = draw_response_times(rng, zone, n)
    if pattern in ("traffic", "combined"):
        response += np.where(planted, pd.Series(traffic).map(TRAFFIC_EFFECT).to_numpy(), 0.0)
    if demand:
        normal_15min = per_hour.mean() / 4
        workload = recent_call_volume(df["dispatch_time"], df["zone"]).to_numpy()
        response += np.where(planted & (workload >= 2 * normal_15min), WORKLOAD_EFFECT, 0.0)
        response += np.where(planted & (units <= 2), LOW_UNIT_EFFECT, 0.0)
    cause = np.where(planted, pattern, "none").astype(object)
    if pattern == "isolated_delay":
        idx = rng.choice(np.flatnonzero(planted), N_ISOLATED_DELAYS, replace=False)
        response[idx] = normal["ucl_min"] * rng.uniform(*ISOLATED_DELAY_X_UCL, len(idx))
        cause[:] = "none"
        cause[idx] = "isolated_delay"

    gap = np.where(units <= 2, rng.uniform(3, 6, n), rng.uniform(0.5, 2, n))
    df["call_received"] = df["dispatch_time"] - pd.to_timedelta((gap * 60).round(), unit="s")
    df["on_scene_time"] = df["dispatch_time"] + pd.to_timedelta((response * 60).round().clip(1), unit="s")
    df["traffic_level"] = traffic
    df["available_units"] = units
    df["priority"] = rng.choice(list(PRIORITY_P), size=n, p=list(PRIORITY_P.values()))
    df["simulated_special_cause"] = cause
    return df


def build(patterns: dict[str, str], seed: int, days: int = DAYS) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = [simulate_zone(rng, z, patterns[z], days) for z in BOROUGHS]
    df = pd.concat(parts).sort_values("dispatch_time").reset_index(drop=True)
    df.insert(0, "incident_id", [f"EMS-{i:06d}" for i in range(1, len(df) + 1)])
    cols = ["incident_id", "call_received", "dispatch_time", "on_scene_time", "zone",
            "traffic_level", "available_units", "priority", "simulated_special_cause"]
    return df[cols]


def stable_operations() -> pd.DataFrame:
    return build({z: "none" for z in BOROUGHS}, seed=101)


def zone_patterns() -> pd.DataFrame:
    return build(PATTERNS, seed=202)


def minimal_input() -> pd.DataFrame:
    """Only the 4 required columns, 21 days of 3 boroughs plus a zone that is not an NYC
    borough ("Harbor Unit", which falls back to its own first 14 days), with planted data
    problems: 2 missing on-scene times, 2 arrivals before dispatch, 1 duplicate id, and a
    non-borough zone ("Ferry Terminal") with only 3 calls."""
    rng = np.random.default_rng(303)
    parts = [simulate_zone(rng, z, "none", 21, volume_scale=0.05)
             for z in ("Bronx", "Brooklyn", "Queens")]
    harbor = simulate_zone(rng, "Brooklyn", "none", 21, volume_scale=0.05)
    harbor["zone"] = "Harbor Unit"
    df = pd.concat(parts + [harbor]).sort_values("dispatch_time").reset_index(drop=True)
    df.insert(0, "incident_id", [f"EMS-{i:06d}" for i in range(1, len(df) + 1)])
    df = df[["incident_id", "dispatch_time", "on_scene_time", "zone"]].copy()
    df["dispatch_time"] = df["dispatch_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["on_scene_time"] = df["on_scene_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df.loc[[10, 20], "on_scene_time"] = ""  # missing
    for i in (30, 40):  # arrival before dispatch
        df.loc[i, "on_scene_time"] = (pd.Timestamp(df.loc[i, "dispatch_time"])
                                      - pd.Timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    dup = df.loc[[50]].copy()
    tiny = pd.DataFrame({
        "incident_id": ["EMS-900001", "EMS-900002", "EMS-900003"],
        "dispatch_time": ["2026-08-05 10:00:00", "2026-08-12 14:30:00", "2026-08-19 18:45:00"],
        "on_scene_time": ["2026-08-05 10:06:10", "2026-08-12 14:37:40", "2026-08-19 18:52:05"],
        "zone": "Ferry Terminal",
    })
    return pd.concat([df, dup, tiny], ignore_index=True)


DATASETS = {
    "stable_operations": stable_operations,
    "zone_patterns": zone_patterns,
    "minimal_input": minimal_input,
}


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for name, make in DATASETS.items():
        df = make()
        path = DATA_DIR / f"{name}.csv"
        df.to_csv(path, index=False, date_format="%Y-%m-%d %H:%M:%S")
        print(f"wrote {path.name}: {len(df)} rows")


if __name__ == "__main__":
    main()
