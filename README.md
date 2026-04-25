# Cooperative Housing Society Portal

Lightweight, mobile-responsive portal built with Flask, SQLite, and Tailwind CSS (CDN), with Google OAuth admin access and Google Drive integration.

## Stack

- Backend: Flask, Flask-Login, Flask-SQLAlchemy, Authlib
- Database: SQLite (`/app/data/db/society.db`)
- Frontend: Jinja templates + Tailwind CSS CDN + vanilla JS
- Deployment: Docker + GHCR + Portainer

## Highlights

- Dynamic branding from `SOCIETY_NAME` in header, page `<title>`, and hero text.
- Hero carousel fetched from Google Drive folder via Drive API (`GOOGLE_DRIVE_API_KEY`).
- Tile-based landing experience including notices, announcements, events, requests, and links.
- Drive document tiles with thumbnail, DB-friendly display name, and direct download.
- Super-admin controlled multi-admin management and recipient email configuration.

## Run locally

1. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Create env file:
   - `cp .env.example .env`
3. Start app:
   - `python3 app/main.py`
4. Open:
   - `http://127.0.0.1:4273/`

## Storage architecture

- DB path: `/app/data/db/society.db`
- Uploads path: `/app/data/uploads`

For local environments that cannot write to `/app`, override:

- `DATABASE_PATH=/workspace/tmp/db/society.db`
- `UPLOADS_PATH=/workspace/tmp/uploads`
