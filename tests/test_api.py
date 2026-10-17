"""API smoke tests: the JSON matches app.qc for the same data."""

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.qc import analyze_incidents

DATA = Path(__file__).resolve().parents[1] / "data"
client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_dashboard_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "EMS Zone Monitor" in resp.text


def test_upload_matches_qc():
    path = DATA / "zone_patterns.csv"
    direct = analyze_incidents(pd.read_csv(path), "monthly")
    with path.open("rb") as f:
        resp = client.post("/api/upload?period=monthly",
                           files={"file": ("zone_patterns.csv", f, "text/csv")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_incidents"] == direct["n_incidents"]
    got = {z["zone"]: (z["status"], z["metrics"]["p90"]) for z in body["zones"]}
    want = {z["zone"]: (z["status"], z["metrics"]["p90"]) for z in direct["zones"]}
    assert got == want


def test_sample_overview_and_zone_detail():
    assert client.post("/api/samples/zone_patterns?period=monthly").status_code == 200
    resp = client.get("/api/zone/Bronx?period=weekly")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "needs_attention"
    assert detail["pattern"] == "Demand / resource pressure"
    assert detail["points"] and "above_ucl" in detail["points"][0]


def test_period_validation():
    assert client.get("/api/overview?period=hourly").status_code == 422


def test_missing_columns_rejected():
    resp = client.post("/api/upload", files={"file": ("bad.csv", b"incident_id,zone\nA,Bronx\n",
                                                      "text/csv")})
    assert resp.status_code == 400
    assert "missing required columns" in resp.json()["detail"]


def test_log_incident_adds_row():
    client.post("/api/samples/minimal_input")
    before = client.get("/api/overview?period=yearly").json()["n_incidents"]
    resp = client.post("/api/incident?period=yearly", json={
        "zone": "Bronx", "dispatch_time": "2026-08-21 23:50:00",
        "on_scene_time": "2026-08-21 23:57:30",
    })
    assert resp.status_code == 200
    assert resp.json()["n_incidents"] == before + 1
