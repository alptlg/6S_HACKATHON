"""Quality-control statistics for EMS dispatch-to-arrival response times."""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, NamedTuple

import numpy as np
import pandas as pd

D2_N2 = 1.128
I_LIMIT_MULT = 2.66  # individuals chart multiplier on MR-bar
MR_UCL_MULT = 3.267  # moving-range UCL multiplier (n=2)
P90_TARGET_MIN = 8.0  # NFPA-style alert threshold (SPEC)
MIN_IMR_POINTS = 2
MIN_ZONE_IMR = 8

REQUIRED_COLUMNS = [
    "incident_id",
    "zone",
    "priority",
    "call_received",
    "dispatch_time",
    "arrival_time",
]


class Limits(NamedTuple):
    """Individuals chart limits on the scale the values were computed in."""

    center: float
    lower: float
    upper: float
    mr_bar: float


class LogIMRLimits(NamedTuple):
    """I-MR limits on log(response time); minutes fields are exp(log) for display."""

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
    return [abs(b - a) for a, b in zip(values, values[1:])]


def control_limits_raw(values: Iterable[float]) -> Limits:
    """I-MR limits on raw minutes (SPEC known-answer check uses 2.66 * MR-bar)."""
    xs = _clean_values(values, MIN_IMR_POINTS)
    center = statistics.fmean(xs)
    mrs = moving_ranges(xs)
    mr_bar = statistics.fmean(mrs) if mrs else 0.0
    return Limits(
        center=center,
        lower=center - I_LIMIT_MULT * mr_bar,
        upper=center + I_LIMIT_MULT * mr_bar,
        mr_bar=mr_bar,
    )


def imr_limits_log(values: Iterable[float]) -> LogIMRLimits:
    """Primary chart method: I-MR on ln(response_min) per SPEC."""
    xs = _clean_values(values, MIN_IMR_POINTS)
    ys = [math.log(x) for x in xs]
    center_log = statistics.fmean(ys)
    mrs = moving_ranges(ys)
    mr_bar_log = statistics.fmean(mrs) if mrs else 0.0
    lcl_log = center_log - I_LIMIT_MULT * mr_bar_log
    ucl_log = center_log + I_LIMIT_MULT * mr_bar_log
    mr_ucl_log = MR_UCL_MULT * mr_bar_log
    return LogIMRLimits(
        center_log=center_log,
        lcl_log=lcl_log,
        ucl_log=ucl_log,
        mr_bar_log=mr_bar_log,
        mr_ucl_log=mr_ucl_log,
        center_min=math.exp(center_log),
        lcl_min=math.exp(lcl_log),
        ucl_min=math.exp(ucl_log),
    )


def imr_chart_points(
    df: pd.DataFrame,
    limits: LogIMRLimits,
    *,
    time_col: str = "call_received",
    value_col: str = "response_min",
    zone_col: str = "zone",
    id_col: str = "incident_id",
) -> list[dict[str, Any]]:
    """One row per incident in time order with log-scale OOC flags."""
    ordered = df.sort_values(time_col).reset_index(drop=True)
    ys = [math.log(float(v)) for v in ordered[value_col]]
    mrs = [None] + moving_ranges(ys)
    points: list[dict[str, Any]] = []
    for i, row in ordered.iterrows():
        y = ys[i]
        ooc = y > limits.ucl_log or y < limits.lcl_log
        mr = mrs[i]
        mr_ooc = mr is not None and mr > limits.mr_ucl_log
        points.append(
            {
                "incident_id": row[id_col],
                "zone": row[zone_col],
                "call_received": str(row[time_col]),
                "response_min": float(row[value_col]),
                "y_log": y,
                "moving_range_log": mr,
                "individual_ooc": ooc,
                "mr_ooc": mr_ooc,
            }
        )
    return points


def percentile_linear(values: Iterable[float], q: float) -> float:
    arr = np.asarray(list(values), dtype=float)
    return float(np.percentile(arr, q, method="linear"))


def response_summary(times: Iterable[float]) -> dict[str, float]:
    xs = _clean_values(times, 1)
    if len(xs) == 1:
        return {
            "mean": xs[0],
            "median": xs[0],
            "stdev": 0.0,
            "p90": xs[0],
            "p95": xs[0],
            "n": 1.0,
        }
    return {
        "mean": statistics.fmean(xs),
        "median": statistics.median(xs),
        "stdev": statistics.stdev(xs),
        "p90": percentile_linear(xs, 90),
        "p95": percentile_linear(xs, 95),
        "n": float(len(xs)),
    }


def add_response_minutes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    call = pd.to_datetime(out["call_received"])
    dispatch = pd.to_datetime(out["dispatch_time"])
    arrival = pd.to_datetime(out["arrival_time"])
    out["response_min"] = (arrival - dispatch).dt.total_seconds() / 60.0
    out["call_received"] = call
    out["dispatch_time"] = dispatch
    out["arrival_time"] = arrival
    return out.sort_values("call_received").reset_index(drop=True)


def validate_incidents(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    work = add_response_minutes(df)
    if work["incident_id"].duplicated().any():
        warnings.append("duplicate incident_id values found")
        work = work.drop_duplicates(subset=["incident_id"], keep="first")

    bad_order = (work["call_received"] > work["dispatch_time"]) | (
        work["dispatch_time"] > work["arrival_time"]
    )
    if bad_order.any():
        n_bad = int(bad_order.sum())
        warnings.append(f"dropped {n_bad} rows with invalid timestamp order")
        work = work.loc[~bad_order]

    if (work["response_min"] <= 0).any():
        n_bad = int((work["response_min"] <= 0).sum())
        warnings.append(f"dropped {n_bad} rows with nonpositive response time")
        work = work.loc[work["response_min"] > 0]

    if len(work) < MIN_IMR_POINTS:
        warnings.append(f"fewer than {MIN_IMR_POINTS} valid rows; I-MR limits unavailable")

    if not work["call_received"].is_monotonic_increasing:
        warnings.append("re-sorted rows by call_received")

    work = work.sort_values("call_received").reset_index(drop=True)
    return work, warnings


def zone_summaries(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for zone, grp in df.groupby("zone", sort=True):
        stats = response_summary(grp["response_min"])
        stats["zone"] = zone
        rows.append(stats)
    return pd.DataFrame(rows).set_index("zone")


def zone_alerts(
    df: pd.DataFrame,
    chart_points: list[dict[str, Any]],
    zone_summary: pd.DataFrame,
    limits: LogIMRLimits | None,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    zones = sorted(df["zone"].unique())
    for zone in zones:
        reasons: list[str] = []
        if limits is not None:
            zone_points = [p for p in chart_points if p["zone"] == zone]
            if any(p["individual_ooc"] for p in zone_points):
                reasons.append("ucl")
        p90 = float(zone_summary.loc[zone, "p90"]) if zone in zone_summary.index else None
        if p90 is not None and p90 > P90_TARGET_MIN:
            reasons.append("p90")
        if reasons:
            alerts.append(
                {
                    "zone": zone,
                    "reasons": reasons,
                    "p90_min": p90,
                    "message": _alert_message(zone, reasons, p90),
                }
            )
    return alerts


def _alert_message(zone: str, reasons: list[str], p90: float | None) -> str:
    parts = []
    if "ucl" in reasons:
        parts.append("at least one response above the log-scale upper control limit")
    if "p90" in reasons:
        parts.append(f"90th percentile {p90:.1f} min exceeds {P90_TARGET_MIN:.0f} min target")
    return f"{zone}: " + "; ".join(parts)


def analyze_incidents(df: pd.DataFrame) -> dict[str, Any]:
    """Full pipeline for API / dashboard (Step 3)."""
    clean, warnings = validate_incidents(df)
    result: dict[str, Any] = {
        "warnings": warnings,
        "n_incidents": len(clean),
        "summary": None,
        "zone_summaries": None,
        "limits_log": None,
        "limits_raw": None,
        "chart_points": [],
        "zone_alerts": [],
    }
    if len(clean) == 0:
        warnings.append("no valid incidents to analyze")
        return result

    times = clean["response_min"].tolist()
    result["summary"] = response_summary(times)
    zs = zone_summaries(clean)
    result["zone_summaries"] = zs.reset_index().to_dict(orient="records")

    if len(clean) >= MIN_IMR_POINTS:
        result["limits_raw"] = control_limits_raw(times)._asdict()
        lim = imr_limits_log(times)
        result["limits_log"] = lim._asdict()
        points = imr_chart_points(clean, lim)
        result["chart_points"] = points
        result["zone_alerts"] = zone_alerts(clean, points, zs, lim)
    else:
        result["zone_alerts"] = zone_alerts(clean, [], zs, None)

    return result
