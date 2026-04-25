# Cooperative Housing Society Portal

Lightweight, mobile-responsive portal built with Flask, SQLite, and Tailwind CSS via CDN.

## Stack

- Backend: Flask + Flask-Login + Authlib + Flask-SQLAlchemy
- Database: SQLite at `/app/data/db/society.db`
- UI: Jinja templates + Tailwind CSS CDN + vanilla JavaScript
- Auth: Google OAuth with multi-admin controls
- Deployment: Docker + GHCR + Portainer stack template

## Core Features

- Landing page with tile-based responsive dashboard.
- Hero carousel fed from a public Google Drive folder URL (with robust parsing fallback).
- Highlighted priority notices from the managing committee.
- Native email actions for service/contact flows:
  - `mailto:` with prefilled subject/body
  - Gmail compose link (`https://mail.google.com/mail/?view=cm&fs=1...`)
- Super Admin from `.env` (`SUPER_ADMIN_EMAIL`) with full access.
- Super Admin UI to add/disable DB-backed admin emails.
- Admin UI for:
  - recipient email configuration
  - notice management
  - file uploads (PDF, DOCX, XLSX, JPG, PNG, ZIP)
- Uploaded file list with file-type icons.

## Local Run

1. Install dependencies:

python3 -m pip install -r requirements.txt

2. Copy env template:

cp .env.example .env

3. Run app:

python3 app/main.py

4. Open:

- Public portal: http://127.0.0.1:4173/
- Admin login: http://127.0.0.1:4173/admin-login
- Health: http://127.0.0.1:4173/api/health

## Storage Paths

- Database (strict): `/app/data/db/society.db`
- Uploads (strict): `/app/data/uploads`

For local development where `/app` may not be writable, set:

- `DATABASE_PATH=/workspace/tmp/db/society.db`
- `UPLOADS_PATH=/workspace/tmp/uploads`

The app still defaults to the strict `/app/data/...` production paths.

## Docker

Build and run:

docker build -t coop-portal:local .
docker run --rm -p 4173:4173 --env-file .env coop-portal:local

## CI/CD

Workflow: `.github/workflows/docker-publish.yml`

- Triggers on push to `main`
- Builds Docker image
- Pushes tags to GHCR:
  - `ghcr.io/<owner>/<repo>:latest`
  - `ghcr.io/<owner>/<repo>:sha-<commit>`

## Portainer Deployment

Use `portainer-stack.yml` as template and update:

- image name (`ghcr.io/OWNER/REPOSITORY:latest`)
- `.env` values

Bind mounts are explicitly separated:

- host `/volume1/docker/gmwebsite/db` -> container `/app/data/db`
- host `/volume1/docker/gmwebsite/uploads` -> container `/app/data/uploads`
