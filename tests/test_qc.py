"""Tests for app.qc: known answers from SPEC.md section 4, degenerate cases, the three synthetic
datasets in data/ (SPEC.md section 7), and the two descriptive charts."""

import math
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
    boxplot_by_group,
    boxplot_series,
    control_limits_raw,
    imr_limits_log,
    longest_run_above,
    pattern_label,
    percentile_linear,
    period_window,
    prepare_incidents,
    recent_call_volume,
    response_summary,
    time_of_day,
    weekday_hour_grid,
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


# --- the three synthetic datasets (SPEC.md section 7) ------------------------------------------
# Each expected result below was produced by running this code on the committed file, so it is
# reproducible, and SPEC.md section 7 states the same numbers.
SYNTHETIC = {
    "no_delay": "noDelayAlexData_2026_24000_synthetic.csv",
    "high_delay": "highDelayAlex_2026_24000_synthetic.csv",
    "stable_operations": "stable_operations_2026_24000_synthetic.csv",
}


def _load(filename: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / filename)


def _zones(key: str, period: str) -> dict:
    return {z["zone"]: z for z in analyze_incidents(_load(SYNTHETIC[key]), period)["zones"]}


@pytest.mark.parametrize("period", ["daily", "weekly", "monthly", "yearly"])
def test_no_delay_dataset_is_normal_in_every_period(period):
    """The tool must not cry wolf: every borough is faster than its real NYC normal."""
    zones = _zones("no_delay", period)
    assert len(zones) == 5
    assert all(z["status"] == STATUS_NORMAL for z in zones.values())
    assert all(z["metrics"]["n_above_ucl"] == 0 for z in zones.values())


def test_no_delay_dataset_in_live_has_too_few_calls_for_staten_isl_and():
    zones = _zones("no_delay", "live")
    assert zones["Staten Island"]["status"] == STATUS_INSUFFICIENT
    assert all(zones[k]["status"] == STATUS_NORMAL
               for k in ("Bronx", "Brooklyn", "Manhattan", "Queens"))


@pytest.mark.parametrize("period", ["weekly", "monthly", "yearly"])
def test_high_delay_dataset_flags_all_five_boroughs(period):
    zones = _zones("high_delay", period)
    assert all(z["status"] == STATUS_ATTENTION for z in zones.values())
    assert all(z["pattern"] for z in zones.values())


def test_high_delay_dataset_at_daily_flags_three_boroughs():
    zones = _zones("high_delay", "daily")
    for name in ("Bronx", "Brooklyn", "Manhattan"):
        assert zones[name]["status"] == STATUS_ATTENTION
    for name in ("Queens", "Staten Island"):
        assert zones[name]["status"] == STATUS_NORMAL  # too few calls yet, not "fine"


def test_stable_operations_dataset_is_normal_daily_and_weekly():
    for period in ("daily", "weekly"):
        zones = _zones("stable_operations", period)
        assert all(z["status"] == STATUS_NORMAL for z in zones.values()), period


def test_stable_operations_dataset_shifts_at_monthly_and_yearly():
    """Named "stable", but the run rule catches a sustained mild shift: 4 of 5 go red."""
    for period in ("monthly", "yearly"):
        zones = _zones("stable_operations", period)
        assert zones["Staten Island"]["status"] == STATUS_NORMAL
        for name in ("Bronx", "Brooklyn", "Manhattan", "Queens"):
            assert zones[name]["status"] == STATUS_ATTENTION, (period, name)
        assert "consecutive daily medians above the centerline" in " ".join(
            zones["Bronx"]["reasons"])


def test_the_tool_recomputes_the_interval_and_ignores_a_provided_column():
    """SPEC section 3: response_time_min is derived, never read. Two files carry a column that
    disagrees with their own timestamps by up to 2.3 minutes; the tool must use the timestamps."""
    raw = _load(SYNTHETIC["high_delay"]).head(50)
    clean, _ = prepare_incidents(raw)
    derived = (pd.to_datetime(raw["on_scene_time"]) - pd.to_datetime(raw["dispatch_time"])
               ).dt.total_seconds().div(60).min()
    assert clean["response_time_min"].min() == pytest.approx(derived, abs=1e-6)


def test_bad_rows_are_dropped_with_a_warning_for_each_kind():
    """No dataset has a broken row now (SPEC section 7), so this is built in memory."""
    good = {"incident_id": "A1", "zone": "Bronx", "dispatch_time": "2026-01-05 10:00:00",
            "on_scene_time": "2026-01-05 10:10:00"}
    raw = pd.DataFrame([
        good,
        {**good, "incident_id": "A1"},                                    # duplicate id
        {**good, "incident_id": "A3", "on_scene_time": None},              # missing time
        {**good, "incident_id": "A4", "on_scene_time": "2026-01-05 09:00:00"},  # before dispatch
    ])
    clean, warnings = prepare_incidents(raw)
    assert len(clean) == 1
    text = " ".join(warnings)
    assert "missing or unreadable" in text
    assert "duplicate incident_id" in text
    assert "not after dispatch_time" in text


# --- H-09: the two descriptive charts ----------------------------------------------------------
def test_boxplot_quartiles_known_answer():
    b = boxplot_series([6, 7, 8, 9, 40])
    assert b["n"] == 5
    assert b["median_min"] == pytest.approx(8.0)
    assert b["q1_min"] == pytest.approx(7.0)
    assert b["q3_min"] == pytest.approx(9.0)


def test_boxplot_fences_whiskers_and_one_outlier():
    """ln values 1.791759, 1.945910, 2.079442, 2.197225, 3.688879; IQR 0.251315;
    fences 1.945910 - 0.376972 = 1.568938 -> 4.80 min and 2.197225 + 0.376972 = 2.574197 ->
    13.12 min. Whiskers reach the last call inside the fences: 6.0 and 9.0. 40 is the outlier."""
    b = boxplot_series([6, 7, 8, 9, 40])
    assert b["lower_fence_min"] == pytest.approx(4.80, abs=0.005)
    assert b["upper_fence_min"] == pytest.approx(13.12, abs=0.005)
    assert b["whisker_low_min"] == pytest.approx(6.0)
    assert b["whisker_high_min"] == pytest.approx(9.0)
    assert b["n_outliers"] == 1
    assert b["outlier_calls"] == [40.0]


def test_boxplot_log_fence_sits_next_to_the_log_imr_ucl():
    """A cross-check, not a coincidence to ignore: on the same five calls the box plot's log
    upper fence is 13.12 min and the log I-MR UCL is 13.21 min. (Both are computed on the
    clean calls [6, 8, 7, 9, 10]; a series with a 40-minute call stretches its own UCL.)"""
    box = boxplot_series(KNOWN)
    ucl = imr_limits_log(KNOWN).ucl_min
    assert ucl == pytest.approx(13.21, abs=0.005)
    assert abs(box["upper_fence_min"] - ucl) < 0.1


def test_boxplot_of_the_spec_known_answer_calls_has_no_outliers():
    b = boxplot_series(KNOWN)  # [6, 8, 7, 9, 10]: same five ln values, so the same fences
    assert b["median_min"] == pytest.approx(8.0)
    assert b["lower_fence_min"] == pytest.approx(4.80, abs=0.005)
    assert b["upper_fence_min"] == pytest.approx(13.12, abs=0.005)
    assert b["n_outliers"] == 0
    assert b["whisker_low_min"] == pytest.approx(6.0)
    assert b["whisker_high_min"] == pytest.approx(10.0)


def test_boxplot_constant_data_has_no_outliers_and_no_inf():
    b = boxplot_series([5.0] * 5)
    assert b["iqr_log"] == 0.0
    assert b["n_outliers"] == 0
    assert b["median_min"] == pytest.approx(5.0)
    assert b["q1_min"] == pytest.approx(5.0)
    assert b["q3_min"] == pytest.approx(5.0)
    assert b["lower_fence_min"] == pytest.approx(5.0)
    assert b["upper_fence_min"] == pytest.approx(5.0)
    assert b["whisker_low_min"] == pytest.approx(5.0)
    assert b["whisker_high_min"] == pytest.approx(5.0)
    assert all(math.isfinite(v) for k, v in b.items() if k.endswith("_min"))


def test_boxplot_needs_five_calls():
    with pytest.raises(ValueError, match="at least 5 values"):
        boxplot_series([6.0, 8.0, 7.0, 9.0])


def _one_month_frame() -> pd.DataFrame:
    """Six calls inside a single calendar month (2026-01), so only one box can be drawn."""
    start = pd.Timestamp("2026-01-05 10:00:00")
    rows = [
        {"incident_id": f"M{i}", "zone": "Bronx",
         "dispatch_time": (start + pd.Timedelta(minutes=7 * i)).strftime("%Y-%m-%d %H:%M:%S"),
         "on_scene_time": (start + pd.Timedelta(minutes=7 * i + 6 + i)).strftime("%Y-%m-%d %H:%M:%S")}
        for i in range(6)
    ]
    return prepare_incidents(pd.DataFrame(rows))[0]


def test_one_box_is_not_a_comparison():
    clean = _one_month_frame()
    assert len(clean) == 6  # every generated row survived validation
    out = boxplot_by_group(clean, "Bronx", "yearly", group="month")
    assert out["comparable"] is False
    assert "one box is not a comparison" in out["note"]
    assert len([g for g in out["groups"] if g["boxplot"] is not None]) == 1
    assert out["groups"][0]["boxplot"]["n"] == 6


def _four_monday_calls() -> pd.DataFrame:
    """SPEC section 4: 10:05 -> 8 min, 10:25 -> 6 min, 10:45 -> 10 min, 11:10 -> 7 min."""
    rows = [
        ("T1", "10:05:00", "10:13:00"), ("T2", "10:25:00", "10:31:00"),
        ("T3", "10:45:00", "10:55:00"), ("T4", "11:10:00", "11:17:00"),
    ]
    frame = pd.DataFrame([{"incident_id": i, "zone": "Testville",
                           "dispatch_time": f"2026-01-05 {d}", "on_scene_time": f"2026-01-05 {s}"}
                          for i, d, s in rows])
    return prepare_incidents(frame)[0]


def test_weekday_hour_grid_known_answer():
    """The (Monday, 10) cell holds [6, 8, 10] -> p90 = 8 + 0.8*(10-8) = 9.6 minutes, and the
    (Monday, 11) cell holds one call -> 7.0 minutes. Both shown here with minimum=1."""
    grid = weekday_hour_grid(_four_monday_calls(), "Testville", "daily", minimum=1)
    monday = grid["weekday_labels"].index("Monday")
    assert grid["cells"][monday][10]["value"] == pytest.approx(9.6)
    assert grid["cells"][monday][10]["n"] == 3
    assert grid["cells"][monday][11]["value"] == pytest.approx(7.0)
    assert grid["n_total"] == 4
    assert grid["stat"] == "p90"


def test_weekday_hour_grid_small_cell_is_none_not_zero():
    """With minimum=3 the 3-call cell is shown and the 1-call cell is not: "not enough calls",
    never 0, and never 7.0 as if one call were the whole distribution."""
    grid = weekday_hour_grid(_four_monday_calls(), "Testville", "daily", minimum=3)
    monday = grid["weekday_labels"].index("Monday")
    assert grid["cells"][monday][10]["value"] == pytest.approx(9.6)
    cell = grid["cells"][monday][11]
    assert cell["n"] == 1
    assert cell["value"] is None
    assert grid["n_cells_with_value"] == 1
    assert grid["n_cells_empty"] == 167


def test_weekday_hour_grid_at_the_default_minimum_shows_nothing_for_four_calls():
    grid = weekday_hour_grid(_four_monday_calls(), "Testville", "daily")
    assert grid["n_cells_with_value"] == 0
    assert grid["n_cells_empty"] == 168
    assert all(c["value"] is None for row in grid["cells"] for c in row)
    assert "no evidence" in grid["note"]
    assert grid["n_total"] == 4  # the calls are still counted, they are just not drawn


def test_weekday_hour_grid_empty_zone_is_all_none_and_does_not_crash():
    grid = weekday_hour_grid(_four_monday_calls(), "Nowhere", "daily")
    assert grid["n_total"] == 0
    assert grid["n_cells_with_value"] == 0
    assert all(c["value"] is None for row in grid["cells"] for c in row)


def test_weekday_hour_grid_refuses_the_mean():
    with pytest.raises(ValueError, match="'p90' or 'median'"):
        weekday_hour_grid(_four_monday_calls(), "Testville", "daily", stat="mean")


def test_weekday_hour_grid_counts_add_up_to_the_period():
    clean, _ = prepare_incidents(_load(SYNTHETIC["no_delay"]))
    for period in ("weekly", "monthly"):
        for zone in ("Bronx", "Queens", "Staten Island"):
            grid = weekday_hour_grid(clean, zone, period)
            in_period = len(period_window(clean, period).loc[lambda d: d["zone"] == zone])
            assert grid["n_total"] == in_period, (zone, period)


def test_weekday_hour_grid_is_thin_at_monthly_and_usable_at_yearly():
    """A real limit of a 7 x 24 grid, not a bug: one zone's monthly window (about 450 calls over
    168 cells) leaves most cells under 20 calls, so they read "not enough calls". Yearly is where
    this chart has enough per cell. The page must say so instead of drawing noise."""
    clean, _ = prepare_incidents(_load(SYNTHETIC["stable_operations"]))
    monthly = weekday_hour_grid(clean, "Bronx", "monthly")
    yearly = weekday_hour_grid(clean, "Bronx", "yearly")
    assert monthly["n_cells_with_value"] < 20
    assert yearly["n_cells_with_value"] > 100
    assert yearly["n_total"] > monthly["n_total"]


def test_new_charts_never_move_a_zone_status():
    """The two charts are descriptive. They must not be able to change a status."""
    raw = _load(SYNTHETIC["high_delay"])
    before = {z["zone"]: z["status"] for z in analyze_incidents(raw, "monthly")["zones"]}
    clean, _ = prepare_incidents(raw)
    for zone in before:
        boxplot_by_group(clean, zone, "monthly", group="weekday")
        boxplot_by_group(clean, zone, "monthly", group="month")
        weekday_hour_grid(clean, zone, "monthly")
    after = {z["zone"]: z["status"] for z in analyze_incidents(raw, "monthly")["zones"]}
    assert before == after


def test_heatmap_separates_the_delayed_file_from_the_normal_one():
    """A planted signal the chart must show (read at Yearly, where the cells are thick enough):
    every Bronx evening cell is slower in the delayed file than in the normal one."""
    evening = range(16, 20)
    worst = {}
    for key in ("no_delay", "high_delay"):
        clean, _ = prepare_incidents(_load(SYNTHETIC[key]))
        grid = weekday_hour_grid(clean, "Bronx", "yearly")
        cells = [grid["cells"][d][h] for d in range(7) for h in evening]
        assert all(c["value"] is not None for c in cells), "yearly cells must be thick enough"
        worst[key] = max(c["value"] for c in cells)
    assert worst["high_delay"] > 3 * worst["no_delay"]


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
