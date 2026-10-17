"""Quality-control statistics for EMS dispatch-to-on-scene response times.

Every number the dashboard shows comes from a function in this file. The API and the page only
call these functions and display the result (see SPEC.md section 4 and docs/proposal.md).

Method in one paragraph:
    response_time_min = on_scene_time - dispatch_time (minutes). Response times are right-skewed,
    so each zone gets an Individuals and Moving Range (I-MR) chart on ln(response_time_min).
    Each NYC borough's "normal" (centerline, limits, p90) comes from 12 months of real FDNY
    incidents (app/nyc_normals.json, built by data/nyc_normals.py). Limits never move with the
    review period: center = mean of the logs, limits = center +/- 2.66 x average moving range,
    MR chart UCL = 3.267 x average moving range. A zone's status in a review period compares the
    calls in that period with its borough's normal: calls above the UCL, a run rule on daily
    medians, and a bootstrap test of the period's p90 against the borough's normal p90.
    A zone that is not an NYC borough falls back to its own first 14 days as the baseline.
"""

from __future__ import annotations

import json
import math
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, NamedTuple

import numpy as np
import pandas as pd

# --- constants (SPEC.md section 4) -------------------------------------------------------------
I_LIMIT_MULT = 2.66  # individuals chart: 3 / d2, d2 = 1.128 for moving ranges of 2
MR_UCL_MULT = 3.267  # moving range chart UCL: D4 for n = 2
NORMALS_PATH = Path(__file__).resolve().parent / "nyc_normals.json"
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 5300  # fixed so the same data always gives the same status
RED_P90_CONFIDENCE = 0.99  # 95% across 5 boroughs, Bonferroni: 1 - 0.05 / 5 per borough
WATCH_P90_CONFIDENCE = 0.95
CHANCE_RATE_ABOVE_UCL = 0.00135  # one-sided 3-sigma tail: share of in-control calls above UCL
RED_MIN_ABOVE_UCL = 3  # Red: at least this many calls above UCL ...
RED_RATE_MULTIPLE = 3.0  # ... AND at least 3x the zone's normal rate of calls above UCL
P90_PRACTICAL_MARGIN = 0.05  # p90 must be at least 5% above normal to matter operationally
MIN_P90_CALLS = 20  # fewer calls in the period -> no p90 test
RUN_RULE_DAYS = 8  # Red: 8 consecutive daily medians above the centerline
BASELINE_DAYS = 14  # control limits come from each zone's first 14 days
MIN_BASELINE_CALLS = 20  # fewer baseline calls -> "insufficient data"
WORKLOAD_WINDOW_MIN = 15  # recent_call_volume = calls in the same zone in the previous 15 minutes
LONG_RESPONSE_FLAG_MIN = 120  # responses longer than this are kept but flagged for review
TRAFFIC_SHARE_MARGIN = 0.15  # traffic marked HIGH if share of High calls >= baseline share + 0.15

REQUIRED_COLUMNS = ["incident_id", "dispatch_time", "on_scene_time", "zone"]
OPTIONAL_COLUMNS = ["call_received", "traffic_level", "available_units", "priority"]
CONDITION_COLUMNS = ["traffic_level", "available_units", "call_received"]

TIME_OF_DAY_BINS = [  # (first hour, last hour, label)
    (0, 5, "Overnight"),
    (6, 9, "Morning"),
    (10, 15, "Day"),
    (16, 19, "Evening peak"),
    (20, 23, "Night"),
]

PERIODS = {  # review period -> length of the window ending at the latest dispatch in the data
    "live": pd.Timedelta(hours=3),
    "daily": pd.Timedelta(days=1),
    "weekly": pd.Timedelta(days=7),
    "monthly": pd.Timedelta(days=30),
    "yearly": pd.Timedelta(days=365),
}

STATUS_NORMAL = "normal"
STATUS_WATCH = "watch"
STATUS_ATTENTION = "needs_attention"
STATUS_INSUFFICIENT = "insufficient_data"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BOX_MIN_CALLS = 5  # a box plot needs at least this many calls to mean anything
HEATMAP_MIN_CELL = 20  # a cell with fewer calls than this reports "not enough calls"
IQR_FENCE_MULT = 1.5  # Tukey's fence: Q1 - 1.5*IQR and Q3 + 1.5*IQR


# --- core I-MR statistics (plain inputs, plain outputs) ---------------------------------------
class Limits(NamedTuple):
    """Individuals chart limits on the scale the values were computed in."""

    center: float
    lower: float
    upper: float
    mr_bar: float


class LogIMRLimits(NamedTuple):
    """I-MR limits on ln(response time); the *_min fields are exp(log) for display."""

    center_log: float
    lcl_log: float
    ucl_log: float
    mr_bar_log: float
    mr_ucl_log: float
    center_min: float
    lcl_min: float
    ucl_min: float


def _clean_values(values: Iterable[float], minimum: int) -> list[float]:
    try:
        xs = [float(v) for v in values]
    except (TypeError, ValueError) as err:
        raise ValueError(f"values must all be numbers: {err}") from None
    if len(xs) < minimum:
        raise ValueError(f"need at least {minimum} values, got {len(xs)}")
    if not all(math.isfinite(x) and x > 0 for x in xs):
        raise ValueError("values must be finite and positive")
    return xs


def moving_ranges(values: list[float]) -> list[float]:
    """|x_i - x_(i-1)| for consecutive values."""
    return [abs(b - a) for a, b in zip(values, values[1:])]


def control_limits_raw(values: Iterable[float]) -> Limits:
    """I-MR limits on raw minutes (kept for the SPEC raw known-answer check)."""
    xs = _clean_values(values, 2)
    center = statistics.fmean(xs)
    mr_bar = statistics.fmean(moving_ranges(xs))
    return Limits(center, center - I_LIMIT_MULT * mr_bar, center + I_LIMIT_MULT * mr_bar, mr_bar)


def imr_limits_log(values: Iterable[float]) -> LogIMRLimits:
    """I-MR limits on ln(response_time_min): the chart the tool uses."""
    xs = _clean_values(values, 2)
    ys = [math.log(x) for x in xs]
    center_log = statistics.fmean(ys)
    mr_bar_log = statistics.fmean(moving_ranges(ys))
    if mr_bar_log == 0:
        raise ValueError("no variation in the baseline (every response time is the same); "
                         "control limits are undefined")
    lcl_log = center_log - I_LIMIT_MULT * mr_bar_log
    ucl_log = center_log + I_LIMIT_MULT * mr_bar_log
    return LogIMRLimits(
        center_log=center_log,
        lcl_log=lcl_log,
        ucl_log=ucl_log,
        mr_bar_log=mr_bar_log,
        mr_ucl_log=MR_UCL_MULT * mr_bar_log,
        center_min=math.exp(center_log),
        lcl_min=math.exp(lcl_log),
        ucl_min=math.exp(ucl_log),
    )


def percentile_linear(values: Iterable[float], q: float) -> float:
    """Percentile with NumPy's default linear interpolation (p90 of [6,8,7,9,10] = 9.6)."""
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        raise ValueError("need at least 1 value for a percentile")
    return float(np.percentile(arr, q, method="linear"))


def response_summary(times: Iterable[float]) -> dict[str, float]:
    """Mean, median, SD, p90, p95, n of response times in minutes."""
    xs = _clean_values(times, 1)
    return {
        "mean": statistics.fmean(xs),
        "median": statistics.median(xs),
        "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
        "p90": percentile_linear(xs, 90),
        "p95": percentile_linear(xs, 95),
        "n": float(len(xs)),
    }


# --- descriptive charts: Tukey box plot and weekday x hour grid --------------------------------
def boxplot_series(values: Iterable[float], *, minimum: int = BOX_MIN_CALLS) -> dict[str, Any]:
    """Tukey box plot of response times, computed on ln(minutes).

    Why the log: on raw minutes Tukey's upper fence falls inside the long right tail of a
    right-skewed response-time distribution, so nearly every long call would look like an
    outlier. On ln(minutes) an outlier is a genuinely unusual call. The returned *_min fields
    are exp() of the log values, so the caller can label the axis in minutes.

    Quartiles use linear interpolation (type 7, the NumPy default; R's boxplot and Excel's
    QUARTILE.INC agree). Fences are Tukey's: Q1 - 1.5*IQR and Q3 + 1.5*IQR, computed on the log
    scale. Whiskers reach the most extreme call inside the fences.

    Degenerate cases: fewer than `minimum` calls raises ValueError (a box of 3 points is not a
    box); constant calls give IQR 0, both fences equal to that constant and zero outliers,
    never inf or NaN.
    """
    xs = _clean_values(values, minimum)
    ys = [math.log(x) for x in xs]
    q1 = percentile_linear(ys, 25)
    median = percentile_linear(ys, 50)
    q3 = percentile_linear(ys, 75)
    iqr = q3 - q1
    lower_fence = q1 - IQR_FENCE_MULT * iqr
    upper_fence = q3 + IQR_FENCE_MULT * iqr

    inside = [x for x, y in zip(xs, ys) if lower_fence <= y <= upper_fence]
    outliers = sorted(x for x, y in zip(xs, ys) if y < lower_fence or y > upper_fence)
    return {
        "n": float(len(xs)),
        "median_min": math.exp(median),
        "q1_min": math.exp(q1),
        "q3_min": math.exp(q3),
        "iqr_log": iqr,
        "lower_fence_min": math.exp(lower_fence),
        "upper_fence_min": math.exp(upper_fence),
        "whisker_low_min": min(inside),
        "whisker_high_min": max(inside),
        "n_outliers": len(outliers),
        "outlier_calls": outliers,
        "scale": "log",
        "fence_rule": "Tukey Q1 - 1.5*IQR, Q3 + 1.5*IQR on ln(minutes)",
    }


def boxplot_by_group(
    df: pd.DataFrame, zone: str, period: str, *, group: str = "weekday",
    minimum: int = BOX_MIN_CALLS,
) -> dict[str, Any]:
    """One Tukey box plot per day of week (or per calendar month) for one zone and period.

    Descriptive only: nothing here may change a zone's status. A group with fewer than
    `minimum` calls gets a reason instead of a box, and if fewer than two groups have a box
    then `comparable` is False - one box is not a comparison, and the page must say so rather
    than draw it.
    """
    if group not in ("weekday", "month"):
        raise ValueError(f"group must be 'weekday' or 'month', got {group!r}")
    window = period_window(df, period)
    zdf = window.loc[window["zone"] == zone]
    key = zdf["dispatch_time"].dt.weekday if group == "weekday" else zdf["dispatch_time"].dt.strftime("%Y-%m")

    groups: list[dict[str, Any]] = []
    labels = WEEKDAYS if group == "weekday" else sorted(key.dropna().unique())
    for label in labels:
        want = WEEKDAYS.index(label) if group == "weekday" else label
        values = zdf.loc[key == want, "response_time_min"].tolist()
        entry: dict[str, Any] = {"group": label, "n": len(values)}
        if len(values) < minimum:
            entry["boxplot"] = None
            entry["reason"] = (f"only {len(values)} calls; at least {minimum} needed "
                               "for a box plot")
        else:
            entry["boxplot"] = boxplot_series(values, minimum=minimum)
            entry["reason"] = None
        groups.append(entry)

    with_box = [g for g in groups if g["boxplot"] is not None]
    return {
        "zone": zone,
        "period": period,
        "group": group,
        "minimum": minimum,
        "groups": groups,
        "comparable": len(with_box) >= 2,
        "note": (None if len(with_box) >= 2 else
                 f"only {len(with_box)} group(s) have enough calls for a box plot; "
                 "one box is not a comparison"),
        "n_total": len(zdf),
    }


def weekday_hour_grid(
    df: pd.DataFrame, zone: str, period: str, *, stat: str = "p90",
    minimum: int = HEATMAP_MIN_CELL,
) -> dict[str, Any]:
    """A 7 x 24 grid (weekday x hour) of a response-time statistic for one zone and period.

    The cell value is the p90 in minutes by default. The mean is deliberately not offered:
    with a right-skewed distribution one 60-minute call moves a mean and does not move a p90.

    A cell with fewer than `minimum` calls gets value None, which means "no evidence", never
    "fast". Callers must render it as "not enough calls" and must not draw a 0. Cells are built
    from rows already passed through prepare_incidents, so the cell counts add up to the calls
    in the period.
    """
    if stat not in ("p90", "median"):
        raise ValueError(f"stat must be 'p90' or 'median', got {stat!r}")
    window = period_window(df, period)
    zdf = window.loc[window["zone"] == zone]

    values: dict[tuple[int, int], list[float]] = {}
    for weekday, hour, rt in zip(
        zdf["dispatch_time"].dt.weekday, zdf["dispatch_time"].dt.hour, zdf["response_time_min"]
    ):
        values.setdefault((int(weekday), int(hour)), []).append(float(rt))

    cells: list[list[dict[str, Any]]] = []
    for weekday in range(7):
        row: list[dict[str, Any]] = []
        for hour in range(24):
            calls = values.get((weekday, hour), [])
            if len(calls) >= minimum:
                value = (percentile_linear(calls, 90) if stat == "p90"
                         else float(np.median(calls)))
                row.append({"value": value, "n": len(calls)})
            else:
                row.append({"value": None, "n": len(calls)})
        cells.append(row)

    with_value = sum(1 for row in cells for c in row if c["value"] is not None)
    return {
        "zone": zone,
        "period": period,
        "stat": stat,
        "minimum": minimum,
        "weekday_labels": WEEKDAYS,
        "hours": list(range(24)),
        "time_of_day_bins": [
            {"first_hour": a, "last_hour": b, "label": label} for a, b, label in TIME_OF_DAY_BINS
        ],
        "cells": cells,
        "n_total": sum(c["n"] for row in cells for c in row),
        "n_cells_with_value": with_value,
        "n_cells_empty": 7 * 24 - with_value,
        "note": (f"a cell shows the {stat} only when it holds at least {minimum} calls; "
                 "an empty cell means no evidence, not a fast response"),
    }


def bootstrap_percentile_ci(
    values: Iterable[float], q: float = 90, confidence: float = 0.95,
    resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the q-th percentile (two-sided).

    Resample the values with replacement `resamples` times, take the q-th percentile of each
    resample, and return the (1-confidence)/2 and 1-(1-confidence)/2 quantiles of those.
    """
    stats = bootstrap_percentiles(values, q, resamples, seed)
    alpha = 1 - confidence
    lo, hi = np.quantile(stats, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def bootstrap_percentiles(
    values: Iterable[float], q: float = 90,
    resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED,
) -> np.ndarray:
    """The q-th percentile of each of `resamples` bootstrap resamples (fixed seed)."""
    arr = np.asarray(list(values), dtype=float)
    if arr.size < 2:
        raise ValueError("need at least 2 values for a bootstrap interval")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(resamples, arr.size))
    return np.percentile(arr[idx], q, axis=1, method="linear")


def longest_run_above(values: Iterable[float], center: float) -> tuple[int, int | None]:
    """Longest run of consecutive values strictly above center: (length, start index)."""
    best, best_start, run, start = 0, None, 0, 0
    for i, v in enumerate(values):
        if v > center:
            if run == 0:
                start = i
            run += 1
            if run > best:
                best, best_start = run, start
        else:
            run = 0
    return best, best_start


# --- derived fields ---------------------------------------------------------------------------
def time_of_day(hour: int) -> str:
    """Overnight 0-5, Morning 6-9, Day 10-15, Evening peak 16-19, Night 20-23."""
    for first, last, label in TIME_OF_DAY_BINS:
        if first <= hour <= last:
            return label
    raise ValueError(f"hour must be 0-23, got {hour}")


def recent_call_volume(dispatch_times: pd.Series, zones: pd.Series) -> pd.Series:
    """Calls dispatched in the same zone during the previous 15 minutes (the call itself excluded).

    A call at time t counts earlier calls with t - 15 min <= time < t.
    """
    out = pd.Series(0, index=dispatch_times.index, dtype=int)
    window = np.timedelta64(WORKLOAD_WINDOW_MIN, "m")
    for _, idx in zones.groupby(zones).groups.items():
        t = dispatch_times.loc[idx].sort_values()
        vals = t.to_numpy(dtype="datetime64[ns]")
        left = np.searchsorted(vals, vals - window, side="left")
        here = np.searchsorted(vals, vals, side="left")
        out.loc[t.index] = here - left
    return out


def prepare_incidents(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate the CSV and add derived fields. Returns (clean rows sorted by dispatch, warnings)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    warnings: list[str] = []
    work = df.copy()
    work["incident_id"] = work["incident_id"].astype(str)
    work["zone"] = work["zone"].astype(str).str.strip()
    for col in ["dispatch_time", "on_scene_time"] + (
        ["call_received"] if "call_received" in work.columns else []
    ):
        work[col] = pd.to_datetime(work[col], errors="coerce")

    n_missing = int(work[["dispatch_time", "on_scene_time"]].isna().any(axis=1).sum())
    if n_missing:
        warnings.append(f"dropped {n_missing} rows with a missing or unreadable dispatch/on-scene time")
        work = work.dropna(subset=["dispatch_time", "on_scene_time"])

    n_dup = int(work["incident_id"].duplicated().sum())
    if n_dup:
        warnings.append(f"dropped {n_dup} rows with a duplicate incident_id")
        work = work.drop_duplicates(subset=["incident_id"], keep="first")

    work["response_time_min"] = (work["on_scene_time"] - work["dispatch_time"]).dt.total_seconds() / 60
    bad = work["response_time_min"] <= 0
    if bad.any():
        warnings.append(f"dropped {int(bad.sum())} rows where on_scene_time is not after dispatch_time")
        work = work.loc[~bad]

    if "call_received" in work.columns:
        late = work["call_received"].notna() & (work["call_received"] > work["dispatch_time"])
        if late.any():
            warnings.append(
                f"{int(late.sum())} rows have call_received after dispatch_time; "
                "their call-to-dispatch time is ignored"
            )
            work.loc[late, "call_received"] = pd.NaT
        work["call_to_dispatch_min"] = (
            (work["dispatch_time"] - work["call_received"]).dt.total_seconds() / 60
        )

    long_calls = work["response_time_min"] > LONG_RESPONSE_FLAG_MIN
    if long_calls.any():
        warnings.append(
            f"{int(long_calls.sum())} responses over {LONG_RESPONSE_FLAG_MIN} min kept; "
            "check for data-entry errors"
        )

    work = work.sort_values("dispatch_time").reset_index(drop=True)
    work["time_of_day"] = work["dispatch_time"].dt.hour.map(time_of_day)
    work["recent_call_volume"] = recent_call_volume(work["dispatch_time"], work["zone"])
    return work, warnings


def available_conditions(df: pd.DataFrame) -> list[str]:
    """Which optional condition columns are present with at least one value."""
    return [c for c in CONDITION_COLUMNS if c in df.columns and df[c].notna().any()]


# --- review period and baseline ---------------------------------------------------------------
def period_window(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Rows whose dispatch_time falls in the review period ending at the latest dispatch."""
    if period not in PERIODS:
        raise ValueError(f"period must be one of {list(PERIODS)}, got {period!r}")
    if df.empty:
        return df
    end = df["dispatch_time"].max()
    return df.loc[df["dispatch_time"] > end - PERIODS[period]]


def baseline_rows(zone_df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """A zone's first 14 days. Returns (rows, full_length) where full_length is False when the
    zone's data spans less than 14 days (then all its rows are the baseline)."""
    start = zone_df["dispatch_time"].min()
    end = start + pd.Timedelta(days=BASELINE_DAYS)
    full = zone_df["dispatch_time"].max() >= end
    return zone_df.loc[zone_df["dispatch_time"] < end], bool(full)


# --- zone status ------------------------------------------------------------------------------
def zone_status(
    window_times: list[float],
    window_days: list[str],
    limits: LogIMRLimits,
    normal_p90: float,
    baseline_rate_above_ucl: float = CHANCE_RATE_ABOVE_UCL,
) -> dict[str, Any]:
    """Status of one zone in one review period.

    window_times: response times (min) of the zone's calls in the period, in time order.
    window_days: the calendar day (YYYY-MM-DD) of each of those calls.
    limits: the zone's normal control limits (NYC borough normal, or its first 14 days).
    normal_p90: the zone's normal 90th percentile (same source as the limits).
    baseline_rate_above_ucl: share of the normal calls above the UCL. The log transform makes
        the data roughly (not exactly) normal, so the "expected by chance" number of calls
        above the UCL uses this rate, never less than 0.135%.
    """
    n = len(window_times)
    if n == 0:
        return {"status": STATUS_INSUFFICIENT, "reasons": ["no calls in this period"], "n": 0}
    logs = [math.log(t) for t in window_times]
    n_above = sum(y > limits.ucl_log for y in logs)
    normal_rate = max(CHANCE_RATE_ABOVE_UCL, baseline_rate_above_ucl)
    expected = normal_rate * n
    beyond_chance = n_above >= 1 and n_above > expected + 3 * math.sqrt(expected)
    rate = n_above / n
    p90_bar = normal_p90 * (1 + P90_PRACTICAL_MARGIN)
    p90 = percentile_linear(window_times, 90)

    daily = (
        pd.DataFrame({"day": window_days, "y": logs}).groupby("day", sort=True)["y"].median()
    )
    run_len, run_start = longest_run_above(daily.tolist(), limits.center_log)
    run_start_day = daily.index[run_start] if run_start is not None else None

    # bootstrap test: is this period's p90 above the zone's normal p90?
    p90_ci95 = p90_ci99 = None
    if n >= MIN_P90_CALLS:
        boot = bootstrap_percentiles(window_times, 90)
        p90_ci95 = tuple(float(v) for v in np.quantile(boot, [0.025, 0.975]))
        p90_ci99 = tuple(float(v) for v in np.quantile(boot, [0.005, 0.995]))

    red, watch = [], []
    if n_above >= RED_MIN_ABOVE_UCL and beyond_chance and rate >= RED_RATE_MULTIPLE * normal_rate:
        red.append(f"{n_above} calls above the upper control limit ({rate:.1%} of calls; "
                   f"normally {normal_rate:.1%})")
    if run_len >= RUN_RULE_DAYS:
        red.append(f"sustained upward shift: {run_len} consecutive daily medians above the "
                   f"centerline since {run_start_day}")
    if p90_ci99 and p90_ci99[0] > p90_bar:
        red.append(f"p90 {p90:.1f} min is significantly above the normal {normal_p90:.1f} min "
                   f"(99% bootstrap interval {p90_ci99[0]:.1f}-{p90_ci99[1]:.1f})")
    if not red:
        if beyond_chance:
            watch.append(f"{n_above} calls above the upper control limit; about "
                         f"{expected:.1f} expected by chance")
        if p90_ci95 and p90_ci95[0] > p90_bar:
            watch.append(f"p90 {p90:.1f} min is above the normal {normal_p90:.1f} min "
                         f"(95% bootstrap interval {p90_ci95[0]:.1f}-{p90_ci95[1]:.1f})")
    status = STATUS_ATTENTION if red else (STATUS_WATCH if watch else STATUS_NORMAL)
    return {
        "status": status,
        "reasons": red or watch or ["within normal range"],
        "n": n,
        "n_above_ucl": n_above,
        "expected_above_ucl": expected,
        "p90": p90,
        "normal_p90": normal_p90,
        "p90_ci95": p90_ci95,
        "p90_ci99": p90_ci99,
        "longest_daily_run": run_len,
        "shift_start_day": run_start_day if run_len >= RUN_RULE_DAYS else None,
    }


# --- possible operational conditions ---------------------------------------------------------
TRAFFIC_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def compare_conditions(baseline: pd.DataFrame, window: pd.DataFrame) -> dict[str, Any]:
    """Compare the period's operating conditions with the zone's baseline.

    Returns {"available": bool, "conditions": [...], "time_of_day": str | None}. Each condition
    has name, level (HIGH / LOW / LONG / NORMAL), current, baseline and flagged.
    """
    present = available_conditions(window)
    conditions: list[dict[str, Any]] = []

    # workload is always derivable from timestamps
    wl_now = float(window["recent_call_volume"].median())
    wl_p75 = float(baseline["recent_call_volume"].quantile(0.75))
    conditions.append({
        "name": "Workload", "unit": "calls in previous 15 min",
        "current": wl_now, "baseline": float(baseline["recent_call_volume"].median()),
        "flagged": wl_now > wl_p75, "level": "HIGH" if wl_now > wl_p75 else "NORMAL",
    })
    if "traffic_level" in present:
        share_now = float((window["traffic_level"] == "High").mean())
        share_base = float((baseline["traffic_level"] == "High").mean())
        flag = share_now >= share_base + TRAFFIC_SHARE_MARGIN
        conditions.append({
            "name": "Traffic", "unit": "share of calls in High traffic",
            "current": share_now, "baseline": share_base,
            "flagged": flag, "level": "HIGH" if flag else "NORMAL",
        })
    if "available_units" in present:
        u_now = float(window["available_units"].median())
        u_p25 = float(baseline["available_units"].quantile(0.25))
        conditions.append({
            "name": "Units", "unit": "available ambulances at dispatch",
            "current": u_now, "baseline": float(baseline["available_units"].median()),
            "flagged": u_now < u_p25, "level": "LOW" if u_now < u_p25 else "NORMAL",
        })
    if "call_received" in present and "call_to_dispatch_min" in window.columns:
        c_now = float(window["call_to_dispatch_min"].median())
        c_p75 = float(baseline["call_to_dispatch_min"].quantile(0.75))
        conditions.append({
            "name": "Call-to-dispatch", "unit": "minutes from call to dispatch",
            "current": c_now, "baseline": float(baseline["call_to_dispatch_min"].median()),
            "flagged": c_now > c_p75, "level": "LONG" if c_now > c_p75 else "NORMAL",
        })

    # time-of-day pattern among long responses (above the baseline p90)
    long_cut = float(baseline["response_time_min"].quantile(0.9))
    long_calls = window.loc[window["response_time_min"] > long_cut, "time_of_day"]
    tod = None
    if len(long_calls) >= 5:
        top = long_calls.value_counts(normalize=True)
        if top.iloc[0] >= 0.5:
            tod = str(top.index[0])
    return {
        "available": bool(set(present) & {"traffic_level", "available_units"}),
        "conditions": conditions,
        "time_of_day": tod,
    }


def pattern_label(status: str, conditions: dict[str, Any]) -> str | None:
    """One-line pattern for a flagged zone (docs/proposal.md section 6)."""
    if status not in (STATUS_WATCH, STATUS_ATTENTION):
        return None
    if not conditions["available"]:
        return "Operational contributing factors are unavailable in the uploaded data"
    flagged = {c["name"] for c in conditions["conditions"] if c["flagged"]}
    traffic = "Traffic" in flagged
    workload = "Workload" in flagged
    resource = bool(flagged & {"Units", "Call-to-dispatch"})
    if traffic and (workload or resource):
        return "Combined operational stress"
    if traffic:
        return "Travel conditions"
    if workload and resource:
        return "Demand / resource pressure"
    if workload:
        return "High-demand pressure"
    if resource:
        return "Resource constraint"
    return "Unexplained special cause: manual incident review recommended"


# --- borough normals (real NYC data) ----------------------------------------------------------
ZONE_ALIASES = {
    "bronx": "Bronx", "brooklyn": "Brooklyn", "manhattan": "Manhattan", "queens": "Queens",
    "staten island": "Staten Island", "richmond / staten island": "Staten Island",
    "richmond": "Staten Island",
}


@lru_cache(maxsize=1)
def load_normals() -> dict[str, Any]:
    """app/nyc_normals.json: per-borough normal statistics from 12 months of FDNY incidents."""
    if not NORMALS_PATH.exists():
        return {"boroughs": {}}
    return json.loads(NORMALS_PATH.read_text())


def borough_normal(zone: str) -> dict[str, Any] | None:
    """The NYC normal for a zone name (case-insensitive borough name), or None."""
    name = ZONE_ALIASES.get(str(zone).strip().lower())
    return load_normals()["boroughs"].get(name) if name else None


def limits_from_normal(normal: dict[str, Any]) -> LogIMRLimits:
    return LogIMRLimits(
        center_log=normal["center_log"], lcl_log=normal["lcl_log"], ucl_log=normal["ucl_log"],
        mr_bar_log=normal["mr_bar_log"], mr_ucl_log=normal["mr_ucl_log"],
        center_min=normal["center_min"], lcl_min=normal["lcl_min"], ucl_min=normal["ucl_min"],
    )


# --- full pipeline used by the API ------------------------------------------------------------
def _insufficient(out: dict[str, Any], reason: str, zdf: pd.DataFrame) -> dict[str, Any]:
    out.update({"status": STATUS_INSUFFICIENT, "reasons": [reason],
                "summary": response_summary(zdf["response_time_min"]) if len(zdf) else None,
                "normal": None, "limits": None, "conditions": None, "pattern": None})
    return out


def analyze_zone(
    clean: pd.DataFrame, zone: str, period: str, *, include_points: bool = False,
) -> dict[str, Any]:
    """Status, statistical reasons, conditions and (optionally) chart points for one zone."""
    zdf = clean.loc[clean["zone"] == zone]
    base, full = baseline_rows(zdf)  # the data's own first 14 days (conditions, fallback limits)
    window = period_window(clean, period)
    window = window.loc[window["zone"] == zone]
    out: dict[str, Any] = {"zone": zone, "period": period, "notes": []}

    nyc = borough_normal(zone)
    if nyc is not None:
        limits = limits_from_normal(nyc)
        normal = {
            "source": "NYC EMS incidents, 12 months (" + load_normals().get("window", {}).get("from", "")[:10]
                      + " to " + load_normals().get("window", {}).get("to_exclusive", "")[:10] + ")",
            "n": nyc["n"], "median": nyc["median_min"], "mean": nyc["mean_min"],
            "stdev": nyc["sd_min"], "p90": nyc["p90_min"], "p95": nyc["p95_min"],
            "rate_above_ucl": nyc["rate_above_ucl"],
        }
    else:
        out["notes"].append(f"{zone}: not an NYC borough, so its first {BASELINE_DAYS} days are "
                            "used as its normal")
        if not full:
            out["notes"].append(f"{zone}: data spans less than {BASELINE_DAYS} days; "
                                "all of it is used as the baseline")
        if len(base) < MIN_BASELINE_CALLS:
            return _insufficient(out, f"only {len(base)} baseline calls; at least "
                                      f"{MIN_BASELINE_CALLS} needed for control limits", zdf)
        try:
            limits = imr_limits_log(base["response_time_min"])
        except ValueError as err:
            return _insufficient(out, str(err), zdf)
        bs = response_summary(base["response_time_min"])
        normal = {"source": f"this zone's first {BASELINE_DAYS} days", **bs,
                  "rate_above_ucl": float((np.log(base["response_time_min"]) > limits.ucl_log).mean())}

    if window.empty:
        return _insufficient(out, "no calls in this period", zdf)
    status = zone_status(
        window["response_time_min"].tolist(),
        window["dispatch_time"].dt.strftime("%Y-%m-%d").tolist(),
        limits, normal["p90"], normal["rate_above_ucl"],
    )
    conditions = compare_conditions(base, window) if len(base) >= MIN_BASELINE_CALLS else None
    out.update({
        "status": status["status"],
        "reasons": status["reasons"],
        "metrics": status,
        "summary": response_summary(window["response_time_min"]),
        "normal": normal,
        "limits": limits._asdict(),
        "conditions": conditions,
        "pattern": pattern_label(status["status"], conditions) if conditions else
                   ("Operational contributing factors are unavailable in the uploaded data"
                    if status["status"] in (STATUS_WATCH, STATUS_ATTENTION) else None),
    })
    if include_points:
        logs = np.log(window["response_time_min"].to_numpy())
        mrs = np.concatenate([[np.nan], np.abs(np.diff(logs))])
        out["points"] = [
            {
                "incident_id": iid, "dispatch_time": str(t), "response_time_min": float(rt),
                "above_ucl": bool(y > limits.ucl_log), "below_lcl": bool(y < limits.lcl_log),
                "moving_range_log": None if np.isnan(mr) else float(mr),
                "mr_above_ucl": bool(not np.isnan(mr) and mr > limits.mr_ucl_log),
            }
            for iid, t, rt, y, mr in zip(
                window["incident_id"], window["dispatch_time"], window["response_time_min"],
                logs, mrs,
            )
        ]
    return out


def analyze_incidents(df: pd.DataFrame, period: str = "monthly") -> dict[str, Any]:
    """Zone overview for the dashboard: one card per zone in the chosen review period."""
    clean, warnings = prepare_incidents(df)
    return overview(clean, warnings, period)


def overview(clean: pd.DataFrame, warnings: list[str], period: str = "monthly") -> dict[str, Any]:
    """Same as analyze_incidents, for rows already passed through prepare_incidents."""
    if period not in PERIODS:
        raise ValueError(f"period must be one of {list(PERIODS)}, got {period!r}")
    warnings = list(warnings)
    normals = load_normals()
    result: dict[str, Any] = {
        "period": period,
        "normals_source": normals.get("source"),
        "normals_url": normals.get("source_url"),
        "normals_window": normals.get("window"),
        "warnings": warnings,
        "n_incidents": int(len(clean)),
        "data_start": str(clean["dispatch_time"].min()) if len(clean) else None,
        "data_end": str(clean["dispatch_time"].max()) if len(clean) else None,
        "conditions_available": bool(set(available_conditions(clean))
                                     & {"traffic_level", "available_units"}),
        "zones": [],
    }
    if clean.empty:
        warnings.append("no valid incidents to analyze")
        return result
    for zone in sorted(clean["zone"].unique()):
        z = analyze_zone(clean, zone, period)
        warnings.extend(z.pop("notes"))
        result["zones"].append(z)
    return result
