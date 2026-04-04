## GolfMeadows Portal - Architecture and Operations Guide

### 1. High-level overview

GolfMeadows is a single-service full-stack web application:

- Backend: FastAPI + SQLAlchemy + SQLite
- Frontend: static HTML/CSS/JavaScript served by FastAPI
- Storage:
  - SQLite DB for structured records
  - filesystem under `/data` for uploaded media

Core goals:

- public resident portal for updates, events, requests, resources, and FAQs
- admin console for content and operational workflows
- low-ops deployment for Portainer and Docker hosts

---

### 2. Runtime architecture

Request flow:

1. Browser requests `index.html` or `admin.html`.
2. FastAPI serves static frontend files from `frontend/`.
3. Frontend JS calls API routes under `/api/v1/...`.
4. Backend reads/writes SQLite and upload storage.
5. Responses return JSON to UI for rendering.

Single-process model:

- Uvicorn worker hosts both API and static frontend.
- No separate frontend build pipeline.

---

### 3. Code layout

- `app/main.py`
  - API routes
  - app startup lifecycle
  - static mounts
- `app/models.py`
  - SQLAlchemy table models
- `app/schemas.py`
  - Pydantic API contracts
- `app/auth.py`
  - local admin auth, JWT/session handling, CSV user sync
- `app/security.py`
  - auth dependency checks (token/JWT; Google auth intentionally disabled in UI workflow)
- `app/seed.py`
  - initial sample content
- `frontend/index.html`, `frontend/main.js`
  - public experience
- `frontend/admin.html`, `frontend/admin.js`
  - admin console (tabbed modules + login-gated access)
- `frontend/styles.css`
  - shared visual system

---

### 4. Data model summary

Main business entities:

- content:
  - `announcements`
  - `events`
  - `resources`
  - `site_settings`
- operations:
  - `service_requests`
  - `service_request_activities`
  - `messages`
- media:
  - `carousel_images`
- auth/admin:
  - `admin_users`
  - `admin_sessions`
- comms/knowledge:
  - `interaction_rota`
  - `faq_entries`

---

### 5. Authentication and authorization

Admin login is form-based local auth:

- `POST /api/v1/admin/auth/login`
- `POST /api/v1/admin/auth/logout`
- `GET /api/v1/admin/session`

Admin route protection:

- all write/ops routes under `/api/v1/admin/*` require valid admin auth.
- frontend admin sections remain hidden until session validation succeeds.

Legacy/fallback:

- raw admin token remains as fallback for emergency access.

---

### 6. Admin user provisioning via CSV

Hidden endpoint:

- `POST /api/v1/admin/users-sync-csv`
- hidden from schema/docs
- expects multipart `file` with users CSV
- requires header: `X-Users-Sync-Secret`

Secret source priority:

1. `GOLFMEADOWS_USERS_SYNC_SECRET` env var
2. site setting key `admin_users_csv_sync_secret`

CSV contract:

- required columns: `email,password`
- optional: `role,is_active`

Behavior:

- upsert by email
- create new users, update existing users
- response includes processed/created/updated counters

---

### 7. Interaction routing and rota

Interaction channels:

- service requests
- contact messages
- FAQ questions

Routing:

- admin-configurable email addresses per channel
- stored in site settings (`interaction_email_*`)
- used by message/request routing metadata and handoff

Rota:

- maintained per interaction category in `interaction_rota`
- each category has primary and optional secondary owners

---

### 8. FAQ lifecycle

Public FAQ:

- rendered on public homepage via `/api/v1/faqs`

Admin FAQ:

- managed in admin dashboard
- includes source linkage to originating message/service request

Auto-FAQ creation:

- when a message is marked `Replied` or `Archived`, backend creates/updates FAQ entries
- when service requests are updated, backend refreshes FAQ entries for recurring issues

---

### 9. UI architecture

Public UI (`index.html` + `main.js`):

- sections:
  - hero/carousel
  - announcements/events/resources
  - service requests
  - contact
  - FAQ

Admin UI (`admin.html` + `admin.js`):

- tabbed modules (no large scrolling-only layout)
- modules:
  - content
  - service operations
  - messages
  - media
  - routing
  - rota
  - FAQ
- login panel separate from operational modules

---

### 10. Deployment model (Portainer + GitHub)

Primary production flow:

1. merge PR to `main`
2. GitHub Action builds/pushes image
3. Portainer stack pulls latest image
4. app boots and initializes schema changes automatically

Key environment variables:

- `GOLFMEADOWS_ADMIN_TOKEN`
- `GOLFMEADOWS_USERS_SYNC_SECRET`
- `GOLFMEADOWS_CORS_ORIGINS`
- `GOLFMEADOWS_DATA_DIR`

---

### 11. Operational checklist before going live

1. verify admin login works on production URL
2. verify CSV user sync with valid secret
3. verify hidden CSV endpoint rejects bad/missing secret
4. verify routing emails and rota assignments are configured
5. publish at least one FAQ and verify public rendering
6. verify service request create/assign/update/takeover flow
7. verify backup policy for `/data` directory

---

### 12. Suggested near-term roadmap

1. email transport integration (actual SMTP/send provider)
2. notification queue/retry for outbound communication
3. richer SLA automation for service requests
4. audit trail UI for admin actions
5. role-based admin permissions per module

