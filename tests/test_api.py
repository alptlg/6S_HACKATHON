"""API smoke tests: the JSON matches app.qc for the same data.

The API is a thin layer, so every number it returns must equal the number the tested function in
app.qc returns for the same rows. These tests compare the two directly.
"""

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import SAMPLES, app
from app.qc import analyze_incidents, boxplot_by_group, prepare_incidents, weekday_hour_grid

DATA = Path(__file__).resolve().parents[1] / "data"
client = TestClient(app)

HIGH_DELAY = DATA / SAMPLES["high_delay"]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_dashboard_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "EMS Zone Monitor" in resp.text


def test_samples_are_the_three_committed_csv_files():
    """SPEC.md section 7: the three datasets are the `*_synthetic.csv` files in data/."""
    body = client.get("/api/samples").json()
    assert body["samples"] == ["no_delay", "stable_operations", "high_delay"]
    for key, filename in body["files"].items():
        assert filename.endswith("_synthetic.csv"), key
        assert (DATA / filename).exists(), (key, filename)


def test_upload_matches_qc():
    direct = analyze_incidents(pd.read_csv(HIGH_DELAY), "monthly")
    with HIGH_DELAY.open("rb") as f:
        resp = client.post("/api/upload?period=monthly",
                           files={"file": (HIGH_DELAY.name, f, "text/csv")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_incidents"] == direct["n_incidents"]
    got = {z["zone"]: (z["status"], z["metrics"]["p90"]) for z in body["zones"]}
    want = {z["zone"]: (z["status"], z["metrics"]["p90"]) for z in direct["zones"]}
    assert got == want


def test_sample_overview_and_zone_detail():
    """The file named "stable_operations" is mildly slow, so at Monthly the run rule fires."""
    resp = client.post("/api/samples/stable_operations?period=monthly")
    assert resp.status_code == 200
    assert client.get("/api/zone/Bronx?period=monthly").status_code == 200
    detail = client.get("/api/zone/Bronx?period=monthly").json()
    assert detail["status"] == "needs_attention"
    assert detail["pattern"].startswith("Unexplained special cause")
    assert detail["points"] and "above_ucl" in detail["points"][0]


def test_the_delayed_sample_is_red_in_every_borough():
    client.post("/api/samples/high_delay?period=weekly")
    body = client.get("/api/overview?period=weekly").json()
    statuses = {z["zone"]: z["status"] for z in body["zones"]}
    assert set(statuses) == {"Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"}
    assert all(s == "needs_attention" for s in statuses.values()), statuses


def test_unknown_sample_is_404():
    assert client.post("/api/samples/zone_patterns").status_code == 404


def test_period_validation():
    assert client.get("/api/overview?period=hourly").status_code == 422


def test_missing_columns_rejected():
    resp = client.post("/api/upload", files={"file": ("bad.csv", b"incident_id,zone\nA,Bronx\n",
                                                      "text/csv")})
    assert resp.status_code == 400
    assert "missing required columns" in resp.json()["detail"]


def test_log_incident_adds_row():
    client.post("/api/samples/high_delay")
    before = client.get("/api/overview?period=yearly").json()["n_incidents"]
    resp = client.post("/api/incident?period=yearly", json={
        "zone": "Bronx", "dispatch_time": "2026-08-21 23:50:00",
        "on_scene_time": "2026-08-21 23:57:30",
    })
    assert resp.status_code == 200
    assert resp.json()["n_incidents"] == before + 1


# --- the two descriptive chart endpoints (H-09) -----------------------------------------------
def test_boxplot_endpoint_matches_qc():
    client.post("/api/samples/high_delay")
    got = client.get("/api/charts/boxplot/Bronx?period=yearly&group=weekday").json()
    clean, _ = prepare_incidents(pd.read_csv(HIGH_DELAY))
    want = boxplot_by_group(clean, "Bronx", "yearly", group="weekday")
    assert got == want
    assert len(got["groups"]) == 7
    assert got["comparable"] is True


def test_heatmap_endpoint_matches_qc_and_nulls_thin_cells():
    client.post("/api/samples/high_delay")
    got = client.get("/api/charts/heatmap/Bronx?period=yearly").json()
    clean, _ = prepare_incidents(pd.read_csv(HIGH_DELAY))
    want = weekday_hour_grid(clean, "Bronx", "yearly")
    assert got == want
    assert got["stat"] == "p90"
    # A thin cell is null (= "not enough calls" on the page), never 0.
    thin = client.get("/api/charts/heatmap/Bronx?period=monthly&minimum=20").json()
    assert thin["n_cells_with_value"] < got["n_cells_with_value"]


def test_boxplot_endpoint_rejects_a_bad_group():
    client.post("/api/samples/high_delay")
    assert client.get("/api/charts/boxplot/Bronx?group=hour").status_code == 422
