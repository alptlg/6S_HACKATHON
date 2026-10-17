#!/bin/bash
# Run the dashboard locally (from repo root on PYTHONPATH).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
