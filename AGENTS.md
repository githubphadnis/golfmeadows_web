# AGENTS.md

## Cursor Cloud specific instructions

### Overview

GolfMeadows Community Portal — a single-service full-stack Python web app (Flask + Flask-SQLAlchemy + SQLite). No external databases, no Node.js, no build step for the frontend.

### Running the dev server

```bash
python3 -m flask --app app.main:app run --host 0.0.0.0 --port 4273
```

Run from the repository root (`/workspace`). The `.env` file must contain `DATABASE_PATH` and `UPLOADS_PATH` pointing to writable local paths (e.g. `/workspace/data/db/society.db` and `/workspace/data/uploads`). Copy `.env.example` to `.env` and add those overrides if not already present.

Public site: `http://127.0.0.1:4273/`  
Admin sign-in: `http://127.0.0.1:4273/admin-login` (Google OAuth required for real login)  
Health check: `GET /api/health`

### Key caveats

- The SQLite database is auto-created on first startup at the path in `DATABASE_PATH`; no migrations needed.
- The system `blinker` package (installed by Debian) conflicts with Flask's requirement for `blinker>=1.9`. Use `pip install --ignore-installed blinker>=1.9.0` before `pip install -r requirements.txt` to work around this on fresh VMs.
- There is no linter or test suite configured in the repository. No `pytest`, `flake8`, `mypy`, or similar tooling is present.
- The frontend is vanilla HTML/CSS/JS (Jinja2 templates + Tailwind CDN) — no build step required.
- The `data/` directory (DB + uploaded images) is created automatically by `app/config.py` on import.
- Default paths in `app/config.py` point to `/app/data/` (Docker context). Override with env vars `DATABASE_PATH` and `UPLOADS_PATH` for local development.
- Admin login requires real Google OAuth credentials; public pages and the booking API work without them.
