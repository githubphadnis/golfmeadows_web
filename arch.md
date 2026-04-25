# Cooperative Housing Society Portal Architecture

## Stack
- Backend: Flask, Flask-Login, Authlib, Flask-SQLAlchemy
- Database: SQLite at `/app/data/db/society.db`
- Frontend: Server-rendered Jinja templates + Tailwind CSS CDN + vanilla JavaScript
- Container: Docker (`python:3.11-slim`)
- CI/CD: GitHub Actions pushes image to GHCR on `main`

## Core Components
- `app/main.py`: App factory, OAuth, routes, admin/public logic
- `app/models.py`: Admins, notices, announcements, events, recipient config, uploaded files
- `app/google_drive.py`: Robust parser/fallback fetcher for public Google Drive folder images
- `app/utils.py`: Upload/file/email helper utilities
- `templates/`: Responsive tile-based UI and admin console
- `static/js/main.js`: Carousel behavior + email link integration

## Storage Split
- Database path: `/app/data/db/society.db`
- Uploads path: `/app/data/uploads`

## Authentication
- Google OAuth sign-in for admins
- Super Admin email from `.env` (`SUPER_ADMIN_EMAIL`)
- Additional admins stored in `admins` table and managed via admin UI
