"""FastAPI entrypoint for Posit Connect (main:app): a thin HTTP layer over qc.py.

No statistics live here. The dashboard is the self-contained static/index.html;
the command-line report is cli.py.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from qc import run_qc
except ModuleNotFoundError:
    from app.qc import run_qc

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Chiblings NYC EMS Response Monitor",
    description=(
        "Six Sigma checks on EMS response times: log I-MR control chart, 95% CI on the "
        "geometric mean, one-sided Cpk against the NFPA 1710 8-minute target."
    ),
    version="0.3.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class QCRequest(BaseModel):
    response_times_min: list[float] = Field(..., min_length=2, description="Response times in minutes, all > 0")


def _json_safe(value: Any) -> Any:
    """inf / nan (e.g. Cpk of constant data) are not valid JSON; send them as null."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/qc")
def qc(req: QCRequest) -> dict[str, Any]:
    """Full QC report (qc.run_qc) for one list of response times."""
    try:
        result = run_qc(req.response_times_min)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _json_safe(dataclasses.asdict(result))
