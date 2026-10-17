"""FastAPI entrypoint: a thin HTTP layer over app.qc (no statistics here)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from qc import analyze_zone, boxplot_by_group, overview, prepare_incidents, weekday_hour_grid
except ModuleNotFoundError:
    from app.qc import (
        analyze_zone,
        boxplot_by_group,
        overview,
        prepare_incidents,
        weekday_hour_grid,
    )

STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# The three test datasets in data/ (SPEC.md section 7). The key is what the UI shows; the file is
# what actually gets loaded, so a judge can point at the same CSV the dashboard is reading.
SAMPLES: dict[str, str] = {
    "no_delay": "noDelayAlexData_2026_24000_synthetic.csv",
    "stable_operations": "stable_operations_2026_24000_synthetic.csv",
    "high_delay": "highDelayAlex_2026_24000_synthetic.csv",
}
Period = Literal["live", "daily", "weekly", "monthly", "yearly"]

app = FastAPI(
    title="Chiblings NYC EMS Zone Monitor",
    description=(
        "Statistical early warning for EMS dispatch-to-on-scene response times: "
        "log I-MR control charts per zone against each NYC borough's normal (12 months of FDNY "
        "incidents), bootstrap p90 test, zone status and possible conditions."
    ),
    version="0.2.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Dataset:
    """The dataset currently loaded (one shared dataset; no database, nothing saved to disk)."""

    def __init__(self) -> None:
        self.name: str | None = None
        self.raw: pd.DataFrame | None = None
        self.clean: pd.DataFrame | None = None
        self.warnings: list[str] = []

    def load(self, name: str, raw: pd.DataFrame) -> None:
        clean, warnings = prepare_incidents(raw)  # raises ValueError on missing columns
        self.name, self.raw, self.clean, self.warnings = name, raw, clean, warnings


current = Dataset()
_sample_cache: dict[str, pd.DataFrame] = {}


class IncidentIn(BaseModel):
    incident_id: str | None = None
    zone: str
    dispatch_time: str
    on_scene_time: str
    call_received: str | None = None
    traffic_level: Literal["Low", "Medium", "High"] | None = None
    available_units: int | None = None
    priority: Literal["High", "Medium", "Low"] | None = None


def _json(payload: dict[str, Any]) -> JSONResponse:
    """JSON response without numpy scalars or NaN."""
    def default(o: Any) -> Any:
        return o.item() if hasattr(o, "item") else str(o)
    text = json.dumps(payload, default=default).replace("NaN", "null")
    return JSONResponse(json.loads(text))


def _require_data() -> None:
    if current.clean is None:
        raise HTTPException(status_code=400, detail="load a sample or upload a CSV first")


def _overview(period: str) -> JSONResponse:
    out = overview(current.clean, current.warnings, period)
    out["dataset"] = current.name
    return _json(out)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/samples")
async def list_samples() -> dict[str, Any]:
    return {
        "samples": list(SAMPLES),
        "files": SAMPLES,
    }


@app.post("/api/samples/{name}")
async def load_sample(
    name: str, period: Period = "monthly"
) -> JSONResponse:
    if name not in SAMPLES:
        raise HTTPException(status_code=404, detail=f"unknown sample {name!r}")
    if name not in _sample_cache:
        path = DATA_DIR / SAMPLES[name]
        if not path.exists():
            raise HTTPException(status_code=500, detail=f"missing dataset file {SAMPLES[name]}")
        _sample_cache[name] = pd.read_csv(path)  # the committed CSV, not a regenerated one
    current.load(name, _sample_cache[name].copy())
    return _overview(period)


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...), period: Period = "monthly",
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="upload a CSV file")
    try:
        raw = pd.read_csv(io.BytesIO(await file.read()))
        current.load(file.filename, raw)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:  # unreadable CSV
        raise HTTPException(status_code=400, detail=f"invalid CSV: {err}") from err
    return _overview(period)


@app.get("/api/overview")
async def get_overview(period: Period = "monthly") -> JSONResponse:
    _require_data()
    return _overview(period)


@app.get("/api/zone/{zone}")
async def get_zone(
    zone: str, period: Period = "monthly"
) -> JSONResponse:
    _require_data()
    if zone not in set(current.clean["zone"]):
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}")
    detail = analyze_zone(current.clean, zone, period, include_points=True)
    return _json(detail)


@app.get("/api/charts/boxplot/{zone}")
async def get_boxplot(
    zone: str,
    period: Period = "monthly",
    group: Literal["weekday", "month"] = "weekday",
) -> JSONResponse:
    """Tukey box plots per weekday (or per calendar month). Descriptive only: this endpoint
    cannot change any zone's status, and the page computes no quartile itself."""
    _require_data()
    if zone not in set(current.clean["zone"]):
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}")
    return _json(boxplot_by_group(current.clean, zone, period, group=group))


@app.get("/api/charts/heatmap/{zone}")
async def get_heatmap(
    zone: str,
    period: Period = "yearly",
    stat: Literal["p90", "median"] = "p90",
    minimum: int = 20,
) -> JSONResponse:
    """The weekday x hour grid for one zone. A cell under `minimum` calls comes back as null,
    which the page renders as "not enough calls" - never as 0."""
    _require_data()
    if zone not in set(current.clean["zone"]):
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}")
    return _json(weekday_hour_grid(current.clean, zone, period, stat=stat, minimum=minimum))


@app.post("/api/incident")
async def log_incident(
    incident: IncidentIn, period: Period = "live"
) -> JSONResponse:
    """Add one incident to the loaded data for this session (kept in memory only)."""
    row = {k: v for k, v in incident.model_dump().items() if v is not None}
    base = current.raw if current.raw is not None else pd.DataFrame()
    row.setdefault("incident_id", f"LOG-{len(base) + 1:06d}")
    try:
        current.load(current.name or "logged incidents", pd.concat([base, pd.DataFrame([row])],
                                                                    ignore_index=True))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return _overview(period)


@app.get("/api/download")
async def download() -> Response:
    """The loaded data, including incidents logged this session, as CSV."""
    _require_data()
    buf = io.StringIO()
    current.raw.to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=incidents.csv"})


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
