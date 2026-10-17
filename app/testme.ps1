# Run the dashboard locally (Windows).
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
& python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
