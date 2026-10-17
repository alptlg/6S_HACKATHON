"""The FastAPI layer that Posit Connect runs (app/main.py:app)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_index_serves_dashboard():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_qc_known_answer():
    r = client.post("/api/qc", json={"response_times_min": [6, 8, 7, 9, 10]})
    assert r.status_code == 200
    body = r.json()
    assert round(body["imr"]["ucl_min"], 2) == 13.21
    assert round(body["ci"]["geo_ci_low"], 3) == 6.127


def test_qc_constant_data_is_valid_json():
    r = client.post("/api/qc", json={"response_times_min": [5, 5, 5]})
    assert r.status_code == 200
    assert r.json()["capability"]["cpk"] is None  # +inf sent as null


def test_qc_rejects_bad_input():
    assert client.post("/api/qc", json={"response_times_min": [7]}).status_code == 422
    assert client.post("/api/qc", json={"response_times_min": [5, 0]}).status_code == 422
