"""Tests for app.qc — hand-checked against SPEC.md section 4."""

from pathlib import Path

import pandas as pd
import pytest

from app.qc import (
    P90_TARGET_MIN,
    analyze_incidents,
    control_limits_raw,
    imr_limits_log,
    percentile_linear,
    response_summary,
    validate_incidents,
)

KNOWN = [6, 8, 7, 9, 10]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_control_limits_raw_spec_known_answer():
    lim = control_limits_raw(KNOWN)
    assert lim.center == pytest.approx(8.0)
    assert lim.mr_bar == pytest.approx(1.5)
    assert lim.upper == pytest.approx(11.99, abs=0.01)
    assert lim.lower == pytest.approx(4.01, abs=0.01)


def test_imr_limits_log_spec_known_answer():
    lim = imr_limits_log(KNOWN)
    assert lim.center_log == pytest.approx(2.0634, abs=1e-3)
    assert lim.mr_bar_log == pytest.approx(0.1945, abs=1e-3)
    assert lim.ucl_log == pytest.approx(2.5807, abs=1e-3)
    assert lim.lcl_log == pytest.approx(1.5461, abs=1e-3)
    assert lim.center_min == pytest.approx(7.87, abs=0.02)
    assert lim.ucl_min == pytest.approx(13.21, abs=0.02)
    assert lim.lcl_min == pytest.approx(4.69, abs=0.02)
    assert lim.mr_ucl_log == pytest.approx(0.6353, abs=1e-3)


def test_percentile_p90_spec():
    assert percentile_linear(KNOWN, 90) == pytest.approx(9.6, abs=0.01)


def test_control_limits_rejects_one_point():
    with pytest.raises(ValueError):
        control_limits_raw([7.0])


def test_imr_constant_log_limits_collapse():
    lim = imr_limits_log([5.0, 5.0, 5.0])
    assert lim.mr_bar_log == pytest.approx(0.0)
    assert lim.ucl_log == pytest.approx(lim.center_log)
    assert lim.lcl_log == pytest.approx(lim.center_log)


def test_validate_drops_bad_timestamps():
    df = pd.DataFrame(
        {
            "incident_id": ["A", "B"],
            "zone": ["North", "North"],
            "priority": ["High", "High"],
            "call_received": ["2026-10-01 08:00:00", "2026-10-01 09:00:00"],
            "dispatch_time": ["2026-10-01 08:02:00", "2026-10-01 09:02:00"],
            "arrival_time": ["2026-10-01 08:01:00", "2026-10-01 09:10:00"],
        }
    )
    clean, warnings = validate_incidents(df)
    assert len(clean) == 1
    assert any("invalid timestamp" in w for w in warnings)


def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / name)


def test_high_delay_zones_flagged():
    out = analyze_incidents(_load("high_delay_operations.csv"))
    flagged = {a["zone"] for a in out["zone_alerts"]}
    assert "South" in flagged
    assert "West" in flagged
    south = next(r for r in out["zone_summaries"] if r["zone"] == "South")
    assert south["p90"] > P90_TARGET_MIN


def test_mixed_has_individual_ooc():
    out = analyze_incidents(_load("mixed_operations.csv"))
    assert any(p["individual_ooc"] for p in out["chart_points"])


def test_normal_operations_runs():
    out = analyze_incidents(_load("normal_operations.csv"))
    assert out["limits_log"] is not None
    assert out["summary"]["n"] >= 40
