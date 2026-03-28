# AGENTS.md

## Cursor Cloud specific instructions

### Overview

GolfMeadows Community Portal — a single-service full-stack Python web app (FastAPI + SQLAlchemy + SQLite). No external databases, no Node.js, no build step for the frontend.

### Running the dev server

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 4173
```

Public site: `http://127.0.0.1:4173/`  
Admin console: `http://127.0.0.1:4173/admin.html`  
API docs (Swagger): `http://127.0.0.1:4173/docs`  
Health check: `GET /api/health`

### Key caveats

- The SQLite database (`data/golfmeadows.db`) is auto-created on first startup; no migrations needed.
- `pip install` may install to `~/.local/bin` (user site-packages). Add `$HOME/.local/bin` to `PATH` if `uvicorn` CLI is not found.
- There is no linter or test suite configured in the repository. No `pytest`, `flake8`, `mypy`, or similar tooling is present.
- The frontend is vanilla HTML/CSS/JS served as static files — no build step required.
- The `data/` directory (DB + uploaded images) is created automatically by `app/config.py` on import.
