"""API smoke tests — JSON matches app.qc for the same CSV."""

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.qc import analyze_incidents

DATA = Path(__file__).resolve().parents[1] / "data" / "normal_operations.csv"


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_analyze_matches_qc():
    client = TestClient(app)
    direct = analyze_incidents(pd.read_csv(DATA))
    with DATA.open("rb") as f:
        resp = client.post("/api/analyze", files={"file": ("normal_operations.csv", f, "text/csv")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_incidents"] == direct["n_incidents"]
    assert body["summary"]["mean"] == direct["summary"]["mean"]
    assert body["limits_log"]["ucl_min"] == direct["limits_log"]["ucl_min"]


def test_dashboard_html():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Response Monitor" in resp.text
    assert "Manhattan" in resp.text


def test_analyze_manhattan_preset():
    client = TestClient(app)
    direct = analyze_incidents(pd.read_csv(DATA))
    resp = client.get("/api/analyze/manhattan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["region_id"] == "manhattan"
    assert body["n_incidents"] == direct["n_incidents"]
