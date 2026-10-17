"""FastAPI entrypoint — thin HTTP layer over app.qc (no statistics here)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from qc import REQUIRED_COLUMNS, analyze_incidents
except ModuleNotFoundError:
    from app.qc import REQUIRED_COLUMNS, analyze_incidents

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Chiblings EMS Response Monitor",
    description="Dispatch-to-arrival response times with log-scale I-MR charts.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_session_incidents: list[dict[str, Any]] = []


class IncidentIn(BaseModel):
    incident_id: str | None = None
    zone: str
    priority: Literal["High", "Medium", "Low"]
    call_received: str
    dispatch_time: str
    arrival_time: str


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure JSON serialization (no numpy scalars)."""
    import json

    return json.loads(json.dumps(payload, default=lambda o: float(o) if hasattr(o, "item") else o))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def dashboard() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=500, detail="dashboard not found")
    return FileResponse(index)


@app.post("/api/analyze")
async def analyze_upload(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="upload a CSV file")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"invalid CSV: {err}") from err
    try:
        result = analyze_incidents(df)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return JSONResponse(_json_safe(result))


@app.get("/api/session")
async def session_status() -> dict[str, Any]:
    return {"count": len(_session_incidents)}


@app.post("/api/incident")
async def log_incident(incident: IncidentIn) -> JSONResponse:
    row = incident.model_dump()
    if not row.get("incident_id"):
        row["incident_id"] = f"LOG-{len(_session_incidents) + 1:04d}"
    _session_incidents.append(row)
    df = pd.DataFrame(_session_incidents)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=500, detail=f"internal schema error: {missing}")
    result = analyze_incidents(df)
    return JSONResponse(_json_safe(result))


@app.delete("/api/session")
async def clear_session() -> dict[str, str]:
    _session_incidents.clear()
    return {"status": "cleared"}


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
