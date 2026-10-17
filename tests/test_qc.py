"""Tests for app.qc: known answers from SPEC.md section 4, degenerate cases, and the planted
patterns in the simulated datasets (docs/proposal.md section 8)."""

from pathlib import Path

import pandas as pd
import pytest

from app.qc import (
    STATUS_ATTENTION,
    STATUS_INSUFFICIENT,
    STATUS_NORMAL,
    STATUS_WATCH,
    analyze_incidents,
    bootstrap_percentile_ci,
    borough_normal,
    control_limits_raw,
    imr_limits_log,
    longest_run_above,
    pattern_label,
    percentile_linear,
    prepare_incidents,
    recent_call_volume,
    response_summary,
    time_of_day,
    zone_status,
)

KNOWN = [6, 8, 7, 9, 10]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# --- known answers (SPEC.md section 4) --------------------------------------------------------
def test_control_limits_raw_known_answer():
    lim = control_limits_raw(KNOWN)
    assert lim.center == pytest.approx(8.0)
    assert lim.mr_bar == pytest.approx(1.5)
    assert lim.upper == pytest.approx(11.99, abs=0.01)
    assert lim.lower == pytest.approx(4.01, abs=0.01)


def test_imr_limits_log_known_answer():
    lim = imr_limits_log(KNOWN)
    assert lim.center_log == pytest.approx(2.0634, abs=1e-3)
    assert lim.mr_bar_log == pytest.approx(0.1945, abs=1e-3)
    assert lim.ucl_log == pytest.approx(2.5807, abs=1e-3)
    assert lim.lcl_log == pytest.approx(1.5461, abs=1e-3)
    assert lim.center_min == pytest.approx(7.87, abs=0.02)
    assert lim.ucl_min == pytest.approx(13.21, abs=0.02)
    assert lim.lcl_min == pytest.approx(4.69, abs=0.02)
    assert lim.mr_ucl_log == pytest.approx(0.6353, abs=1e-3)


def test_p90_known_answer():
    assert percentile_linear(KNOWN, 90) == pytest.approx(9.6, abs=0.01)


def test_response_time_from_timestamps():
    df = pd.DataFrame({
        "incident_id": ["A"], "zone": ["Bronx"],
        "dispatch_time": ["2026-09-14 17:42:10"], "on_scene_time": ["2026-09-14 17:51:55"],
    })
    clean, _ = prepare_incidents(df)
    assert clean.loc[0, "response_time_min"] == pytest.approx(9.75)


def test_call_to_dispatch_from_timestamps():
    df = pd.DataFrame({
        "incident_id": ["A"], "zone": ["Bronx"], "call_received": ["2026-09-14 17:40:40"],
        "dispatch_time": ["2026-09-14 17:42:10"], "on_scene_time": ["2026-09-14 17:51:55"],
    })
    clean, _ = prepare_incidents(df)
    assert clean.loc[0, "call_to_dispatch_min"] == pytest.approx(1.5)


def test_recent_call_volume_counts_previous_15_minutes_same_zone():
    t = pd.to_datetime(pd.Series([
        "2026-08-01 10:00", "2026-08-01 10:05", "2026-08-01 10:14", "2026-08-01 10:20",
        "2026-08-01 10:05",
    ]))
    z = pd.Series(["Bronx", "Bronx", "Bronx", "Bronx", "Queens"])
    # 10:20 counts 10:05 and 10:14 (10:00 is 20 min earlier); Queens is separate
    assert recent_call_volume(t, z).tolist() == [0, 1, 2, 2, 0]


def test_time_of_day_bins():
    assert [time_of_day(h) for h in (0, 6, 12, 17, 22)] == [
        "Overnight", "Morning", "Day", "Evening peak", "Night"]


def test_longest_run_above():
    assert longest_run_above([1, 3, 3, 3, 1, 3], 2) == (3, 1)


# --- degenerate cases -------------------------------------------------------------------------
def test_limits_reject_one_point():
    with pytest.raises(ValueError):
        imr_limits_log([7.0])


def test_constant_data_has_no_control_limits():
    with pytest.raises(ValueError, match="no variation"):
        imr_limits_log([5.0, 5.0, 5.0])


def test_constant_baseline_zone_is_insufficient_not_flagged():
    times = pd.date_range("2026-08-01", periods=40, freq="h")
    df = pd.DataFrame({
        "incident_id": [f"C{i}" for i in range(40)], "zone": "Test Zone",  # not a borough
        "dispatch_time": times, "on_scene_time": times + pd.Timedelta(minutes=5),
    })
    zone = analyze_incidents(df, "yearly")["zones"][0]
    assert zone["status"] == STATUS_INSUFFICIENT
    assert "no variation" in zone["reasons"][0]


def test_single_value_summary_has_zero_sd():
    s = response_summary([7.0])
    assert s["stdev"] == 0.0 and s["p90"] == 7.0


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="missing required columns"):
        prepare_incidents(pd.DataFrame({"incident_id": ["A"], "zone": ["Bronx"]}))


# --- status rules on small planted cases ------------------------------------------------------
LIM = imr_limits_log([6.0, 6.5, 5.5, 6.2, 5.8, 6.1, 5.9, 6.4])  # baseline around 6 min


def test_one_isolated_outlier_is_not_red():
    times = [6.0] * 199 + [30.0]
    s = zone_status(times, ["2026-08-01"] * 200, LIM, normal_p90=50.0)
    assert s["n_above_ucl"] == 1
    assert s["status"] != STATUS_ATTENTION


def test_many_points_above_ucl_is_red():
    times = [6.0] * 90 + [30.0] * 10  # 10% above UCL
    s = zone_status(times, ["2026-08-01"] * 100, LIM, normal_p90=50.0)
    assert s["status"] == STATUS_ATTENTION


def test_p90_clearly_above_normal_is_red():
    # every call 9 min: the bootstrap interval is 9-9, entirely above a normal p90 of 7
    s = zone_status([9.0] * 20, ["2026-08-01"] * 20, LIM, normal_p90=7.0)
    assert s["p90_ci99"] == (9.0, 9.0)
    assert s["status"] == STATUS_ATTENTION


def test_p90_equal_to_normal_is_not_flagged():
    s = zone_status([6.0, 6.5, 5.5, 6.2, 5.8] * 20, ["2026-08-01"] * 100, LIM, normal_p90=6.5)
    assert s["status"] == STATUS_NORMAL


def test_bootstrap_interval_contains_sample_p90_and_is_reproducible():
    data = [6, 8, 7, 9, 10] * 20
    lo, hi = bootstrap_percentile_ci(data, 90, 0.95)
    assert lo <= percentile_linear(data, 90) <= hi
    assert bootstrap_percentile_ci(data, 90, 0.95) == (lo, hi)  # fixed seed


def test_bootstrap_needs_two_values():
    with pytest.raises(ValueError):
        bootstrap_percentile_ci([7.0])


def test_run_of_8_daily_medians_is_red():
    days = [f"2026-08-{d:02d}" for d in range(1, 9) for _ in range(5)]
    s = zone_status([6.6] * 40, days, LIM, normal_p90=50.0)  # every day slightly above center
    assert s["longest_daily_run"] == 8
    assert s["status"] == STATUS_ATTENTION


def test_pattern_labels():
    def cond(*flagged, available=True):
        names = ["Workload", "Traffic", "Units", "Call-to-dispatch"]
        return {"available": available,
                "conditions": [{"name": n, "flagged": n in flagged} for n in names]}
    assert pattern_label(STATUS_NORMAL, cond()) is None
    assert pattern_label(STATUS_ATTENTION, cond("Traffic")) == "Travel conditions"
    assert pattern_label(STATUS_ATTENTION, cond("Workload")) == "High-demand pressure"
    assert pattern_label(STATUS_ATTENTION, cond("Units")) == "Resource constraint"
    assert pattern_label(STATUS_ATTENTION, cond("Workload", "Units")) == "Demand / resource pressure"
    assert pattern_label(STATUS_ATTENTION, cond("Traffic", "Units")) == "Combined operational stress"
    assert pattern_label(STATUS_WATCH, cond()).startswith("Unexplained special cause")
    assert pattern_label(STATUS_WATCH, cond(available=False)).startswith("Operational contributing")


# --- planted patterns in the simulated datasets -----------------------------------------------
def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{name}.csv")


def _zones(name: str, period: str) -> dict:
    return {z["zone"]: z for z in analyze_incidents(_load(name), period)["zones"]}


@pytest.mark.parametrize("period", ["live", "daily", "weekly", "monthly", "yearly"])
def test_stable_operations_all_normal(period):
    zones = _zones("stable_operations", period)
    assert len(zones) == 5
    assert all(z["status"] == STATUS_NORMAL for z in zones.values())


def test_zone_patterns_monthly():
    z = _zones("zone_patterns", "monthly")
    assert z["Staten Island"]["status"] == STATUS_NORMAL
    assert z["Queens"]["status"] == STATUS_ATTENTION
    assert z["Queens"]["pattern"] == "Travel conditions"
    assert z["Bronx"]["status"] == STATUS_ATTENTION
    assert z["Bronx"]["pattern"] == "Demand / resource pressure"
    assert z["Brooklyn"]["status"] == STATUS_ATTENTION
    assert z["Brooklyn"]["pattern"] == "Combined operational stress"
    assert z["Manhattan"]["status"] == STATUS_WATCH
    assert z["Manhattan"]["pattern"].startswith("Unexplained special cause")


def test_zone_patterns_shift_starts_on_day_40():
    bronx = _zones("zone_patterns", "monthly")["Bronx"]
    assert bronx["metrics"]["shift_start_day"] == "2026-09-09"  # day 40 = Aug 1 + 39 days


def test_minimal_input_works_without_optional_columns():
    out = analyze_incidents(_load("minimal_input"), "monthly")
    z = {x["zone"]: x for x in out["zones"]}
    assert out["conditions_available"] is False
    assert z["Ferry Terminal"]["status"] == STATUS_INSUFFICIENT  # 3 calls, not a borough
    assert all(z[k]["status"] == STATUS_NORMAL for k in ("Bronx", "Brooklyn", "Queens", "Harbor Unit"))
    assert z["Bronx"]["normal"]["source"].startswith("NYC")
    assert z["Harbor Unit"]["normal"]["source"].startswith("this zone's first 14 days")
    text = " ".join(out["warnings"])
    assert "missing or unreadable" in text
    assert "duplicate incident_id" in text
    assert "not after dispatch_time" in text
    assert "Harbor Unit: not an NYC borough" in text


# --- borough normals from real NYC data -------------------------------------------------------
def test_borough_normals_loaded_for_all_five_boroughs():
    for name in ("Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"):
        nyc = borough_normal(name)
        assert nyc["n"] > 50_000
        assert nyc["lcl_min"] < nyc["median_min"] < nyc["p90_min"] < nyc["ucl_min"]
    assert borough_normal("BRONX") == borough_normal("Bronx")  # names are case-insensitive
    assert borough_normal("Richmond / Staten Island") == borough_normal("Staten Island")
    assert borough_normal("Harbor Unit") is None


def test_borough_limits_follow_the_i_mr_formula():
    nyc = borough_normal("Queens")
    assert nyc["ucl_log"] == pytest.approx(nyc["center_log"] + 2.66 * nyc["mr_bar_log"])
    assert nyc["lcl_log"] == pytest.approx(nyc["center_log"] - 2.66 * nyc["mr_bar_log"])
    assert nyc["mr_ucl_log"] == pytest.approx(3.267 * nyc["mr_bar_log"])
