"""
Generate synthetic EMS incident CSVs for Chiblings (Prompt #2).
Run from repo root:
  ..\\venv_sigma\\python.exe data\\generate_datasets.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 5300
N_ROWS = 60
ZONES = ["North", "South", "East", "West", "Central"]
PRIORITIES = ["High", "Medium", "Low"]
PRIORITY_P = [0.6, 0.3, 0.1]
START = pd.Timestamp("2026-10-01 08:00:00")
SPAN_DAYS = 21
SHIFT_ON = pd.Timestamp("2026-10-12 00:00:00")  # high_delay: South/West slower after this
SPIKE_MINUTES = [18.5, 22.0, 16.0, 24.5, 19.0, 21.0]  # mixed_operations spikes
SPIKE_AT_ROWS = [12, 28, 35, 41, 52, 57]  # 0-based indices after sort by call_received

OUT_DIR = Path(__file__).resolve().parent


def _rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


def _sample_lognormal_minutes(rng: np.random.Generator, median_min: float, sigma: float) -> float:
    """Log-normal with approximate median `median_min` (minutes), always > 0."""
    mu = np.log(median_min)
    val = float(rng.lognormal(mean=mu, sigma=sigma))
    return max(val, 0.5)


def _call_times(rng: np.random.Generator, n: int) -> pd.DatetimeIndex:
    """Spread incidents across SPAN_DAYS so high_delay can use a mid-month shift."""
    span_min = SPAN_DAYS * 24 * 60
    offsets = np.sort(rng.uniform(0, span_min, size=n))
    return START + pd.to_timedelta(offsets, unit="m")


def _build_frame(
    rng: np.random.Generator,
    response_min_fn,
) -> pd.DataFrame:
    calls = _call_times(rng, N_ROWS)
    zones = rng.choice(ZONES, size=N_ROWS)
    priorities = rng.choice(PRIORITIES, size=N_ROWS, p=PRIORITY_P)

    rows = []
    for i in range(N_ROWS):
        call = calls[i]
        zone = zones[i]
        priority = priorities[i]
        dispatch_lag = float(rng.uniform(1.0, 3.0))
        response_min = float(response_min_fn(i, call, zone, priority, rng))
        dispatch = call + pd.Timedelta(minutes=dispatch_lag)
        arrival = dispatch + pd.Timedelta(minutes=response_min)
        rows.append(
            {
                "incident_id": f"EMS-2026-{i + 1:04d}",
                "zone": zone,
                "priority": priority,
                "call_received": call.strftime("%Y-%m-%d %H:%M:%S"),
                "dispatch_time": dispatch.strftime("%Y-%m-%d %H:%M:%S"),
                "arrival_time": arrival.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    df = pd.DataFrame(rows).sort_values("call_received").reset_index(drop=True)
    # Re-number IDs in time order for readability
    df["incident_id"] = [f"EMS-2026-{j + 1:04d}" for j in range(len(df))]
    return df


def normal_response(_i, _call, _zone, _priority, rng) -> float:
    return _sample_lognormal_minutes(rng, median_min=6.0, sigma=0.22)


def high_delay_response(i, call, zone, _priority, rng) -> float:
    if zone in ("South", "West") and call >= SHIFT_ON:
        return _sample_lognormal_minutes(rng, median_min=11.5, sigma=0.25)
    return _sample_lognormal_minutes(rng, median_min=6.0, sigma=0.22)


def mixed_response(_i, _call, _zone, _priority, rng) -> float:
    return _sample_lognormal_minutes(rng, median_min=6.0, sigma=0.22)


def _inject_spikes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for row_idx, minutes in zip(SPIKE_AT_ROWS, SPIKE_MINUTES, strict=True):
        dispatch = pd.to_datetime(df.at[row_idx, "dispatch_time"])
        df.at[row_idx, "arrival_time"] = (dispatch + pd.Timedelta(minutes=minutes)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    return df


def validate(df: pd.DataFrame, name: str) -> None:
    for col in ["incident_id", "zone", "priority", "call_received", "dispatch_time", "arrival_time"]:
        if df[col].isna().any():
            raise ValueError(f"{name}: missing values in {col}")
    if df["incident_id"].duplicated().any():
        raise ValueError(f"{name}: duplicate incident_id")
    call = pd.to_datetime(df["call_received"])
    disp = pd.to_datetime(df["dispatch_time"])
    arr = pd.to_datetime(df["arrival_time"])
    if not (call <= disp).all() or not (disp <= arr).all():
        raise ValueError(f"{name}: invalid timestamp order")
    rt = (arr - disp).dt.total_seconds() / 60.0
    if (rt <= 0).any():
        raise ValueError(f"{name}: nonpositive response time")
    if not call.is_monotonic_increasing:
        raise ValueError(f"{name}: rows not sorted by call_received")


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    disp = pd.to_datetime(df["dispatch_time"])
    arr = pd.to_datetime(df["arrival_time"])
    df = df.copy()
    df["response_min"] = (arr - disp).dt.total_seconds() / 60.0
    return df.groupby("zone")["response_min"].agg(["count", "mean", lambda s: np.percentile(s, 90)]).rename(
        columns={"<lambda_0>": "p90"}
    )


def main() -> None:
    rng = _rng()
    mixed = _build_frame(np.random.default_rng(SEED + 2), mixed_response)
    mixed = _inject_spikes(mixed)
    datasets = {
        "normal_operations.csv": _build_frame(rng, normal_response),
        "high_delay_operations.csv": _build_frame(np.random.default_rng(SEED + 1), high_delay_response),
        "mixed_operations.csv": mixed,
    }
    for fname, df in datasets.items():
        validate(df, fname)
        path = OUT_DIR / fname
        df.to_csv(path, index=False)
        print(f"Wrote {path} ({len(df)} rows)")
        print(summarize(df).round(2).to_string())
        print()


if __name__ == "__main__":
    main()
