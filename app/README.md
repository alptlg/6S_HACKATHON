# Chiblings EMS Response Monitor (FastAPI)

Dispatch-to-arrival response time dashboard with log-scale I-MR charts. Statistics live in `qc.py`; HTTP in `main.py`.

## Run locally

From repo root with `venv_sigma` active:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or:

```powershell
.\app\testme.ps1
```

Open http://localhost:8000 — upload a CSV from `../data/`.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| GET | `/health` | Smoke check |
| POST | `/api/analyze` | CSV upload → JSON analysis |
| POST | `/api/incident` | Log one row (in-memory session) |
| DELETE | `/api/session` | Clear session |
| GET | `/docs` | OpenAPI |

## Posit Connect

**Entrypoint:** `main:app` · **Python:** `3.12` (`.python-version` must match manifest).

### GitHub Actions (recommended after first deploy)

1. Repo **Settings → Secrets → Actions**: add `CONNECT_SERVER` and `CONNECT_API_KEY` (from event staff).
2. Push to `main` — workflow `.github/workflows/deploy-fastapi.yml` ships `app/manifest.json` unchanged.
3. Re-run `manifestme.sh` and commit whenever `requirements.txt` or bundled files change.

### Local deploy (fastest first URL)

Gitignored `.env` at repo root:

```
CONNECT_SERVER=https://...
CONNECT_API_KEY=...
```

```bash
cd app
./manifestme.sh
./deployme.sh
```

In Connect, set access so judges can open the URL without logging in.

## Tests

From repo root: `pytest tests` (includes API smoke test).
