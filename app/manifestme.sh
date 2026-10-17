#!/bin/bash
# Write Posit Connect manifest for this FastAPI app (run from app/).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python -m pip install rsconnect-python
rsconnect write-manifest fastapi . --entrypoint main:app --overwrite
echo "Done. Commit manifest.json in app/"
