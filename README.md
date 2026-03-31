# GolfMeadows Community Portal

Full-stack website for **GolfMeadows Housing Society (Panvel, Maharashtra)** with:

- modern public landing page and dynamic content sections
- optimized carousel uploads (server-side resize/compress)
- persistent storage for media and data
- positive **Service Requests** workflow (instead of complaints)
- admin console for announcements, events, resources, messages, and request operations
- minimal admin authentication (token + optional Google ID token validation)
- API-first design for future integration into **CONDO** (open-source housing management platform)

## Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Image processing**: Pillow (EXIF normalize, resize, WebP compression)
- **Frontend**: Vanilla HTML/CSS/JS (public + admin)
- **Storage**: Filesystem + DB inside configurable data directory
- **Containerization**: Docker + docker-compose
- **CI/CD**: GitHub Actions + GHCR + optional Portainer webhook trigger

## Project Structure

```text
app/
  main.py            # API and static serving
  models.py          # Database models
  schemas.py         # API schema contracts
  image_utils.py     # Upload optimization pipeline
  seed.py            # Initial seeded content
frontend/
  index.html         # Public site
  admin.html         # Admin console
  styles.css         # Shared styles
  main.js            # Public site JS client
  admin.js           # Admin console JS client
deployment/
  docker-compose.portainer.yml      # Portainer stack compose
  .env.example                       # Deployment environment template
  cloudflared-config.example.yml     # Cloudflare tunnel config template
.github/workflows/
  docker-deploy.yml    # Build/push image and trigger Portainer webhook
scripts/
  deploy-local.sh      # Helper for local server deployment
data/
  golfmeadows.db       # SQLite DB (created at runtime)
  uploads/carousel/    # Optimized uploaded images
```

## Run locally (without Docker)

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Start the app:

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 4173
```

3. Open:

- Public site: `http://127.0.0.1:4173/`
- Admin site: `http://127.0.0.1:4173/admin.html`
- API docs: `http://127.0.0.1:4173/docs`

### Admin auth and CORS setup (recommended)

Set these before starting the server:

```bash
export GOLFMEADOWS_ADMIN_TOKEN="replace-with-strong-random-secret"
export GOLFMEADOWS_CORS_ORIGINS="http://127.0.0.1:4173,http://localhost:4173,https://golfmeadows.org,https://www.golfmeadows.org,https://admin.golfmeadows.org,https://*.golfmeadows.org"
```

Optional Google admin sign-in (ID token verification):

```bash
export GOLFMEADOWS_GOOGLE_CLIENT_ID="your-google-oauth-client-id.apps.googleusercontent.com"
export GOLFMEADOWS_ADMIN_GOOGLE_EMAILS="admin@golfmeadows.org,ops@golfmeadows.org"
```

Notes:
- Public APIs are read/submission routes (for resident-facing site).
- Admin write/ops APIs are under `/api/v1/admin/*` and require auth.
- For Portainer repo deployments where you only set `GOLFMEADOWS_ADMIN_TOKEN`, local form-login
  now auto-bootstraps with:
  - email: `admin@golfmeadows.local`
  - password: same value as `GOLFMEADOWS_ADMIN_TOKEN`
  You can log in immediately and then create/reset dedicated admin users from the Admin Users panel.

## Run with Docker

```bash
docker compose up -d --build
```

Open:

- Public site: `http://127.0.0.1:4173/`
- Admin site: `http://127.0.0.1:4173/admin.html`

## Persistent volume location

By default, data is stored in `./data`.

To mount to a different volume/location, set:

```bash
export GOLFMEADOWS_DATA_DIR=/path/to/volume
```

In Docker/Portainer deployments, bind this to a host path or named volume.

## GitHub Actions CI/CD

Workflow: `.github/workflows/docker-deploy.yml`

On pushes to `main`:

1. builds Docker image
2. pushes to GHCR:
   - `ghcr.io/<owner>/<repo>:latest`
   - `ghcr.io/<owner>/<repo>:sha-<shortsha>`
3. optionally triggers Portainer webhook if secret exists

### Required repository settings and secrets

- Repository **Actions permissions** must allow write to packages.
- `PORTAINER_WEBHOOK_URL` (optional, but needed for auto-redeploy)

## Portainer auto-pull / webhook deployment

1. In Portainer, create stack from `deployment/docker-compose.portainer.yml`.
2. Set env variables from `deployment/.env.example`.
3. Ensure your host is logged in to GHCR:

```bash
echo "<GH_PAT_WITH_read:packages>" | docker login ghcr.io -u "<github_username>" --password-stdin
```

4. Enable **Webhook** for the stack and copy URL.
5. Add URL as GitHub secret: `PORTAINER_WEBHOOK_URL`.
6. Each successful CI build on `main` will call webhook and refresh stack.

### Cloudflare Tunnel + domain (`golfmeadows.org`)

Recommended DNS/Tunnel setup:
- `golfmeadows.org` -> proxied CNAME to your tunnel hostname
- `www.golfmeadows.org` -> proxied CNAME to your tunnel hostname
- `admin.golfmeadows.org` -> proxied CNAME to your tunnel hostname

Use `deployment/cloudflared-config.example.yml` and set hostname entries accordingly.

### Push this branch to `main`

The CI workflow runs on `main`, so merge this branch into `main` to activate automated build/deploy.

## Cloudflare Tunnel test plan

Use `deployment/cloudflared-config.example.yml` as template.

Validate:

- `https://golfmeadows.org/` -> public homepage
- `https://admin.golfmeadows.org/admin.html` -> admin page
- `https://golfmeadows.org/api/health` -> `{"status":"ok", ...}`
- upload image and verify persistence after container restart

## Bring site live on your personal server (quick runbook)

1. Install Docker + Docker Compose plugin on the machine.
2. Clone repo to server and copy env template:

```bash
cp deployment/.env.example deployment/.env
```

3. Edit `deployment/.env` for your machine paths/domain.
4. Deploy:

```bash
./scripts/deploy-local.sh
```

5. Confirm:

```bash
curl -fsS http://127.0.0.1:4173/api/health
```

## Service Requests lifecycle

Residents can submit service requests and track them via ticket refs (`GM-SR-00001`).
Admin can:

- update status (`Submitted`, `In Review`, `In Progress`, `Resolved`, `Closed`)
- add internal notes
- append timeline updates (activities)

## API route split (public vs admin)

Public:
- `GET /api/v1/announcements`
- `GET /api/v1/events`
- `GET /api/v1/resources`
- `GET /api/v1/carousel`
- `POST /api/v1/public/service-requests`
- `GET /api/v1/public/service-requests/recent`
- `GET /api/v1/public/service-requests/{ticket_ref}`
- `POST /api/v1/public/messages`

Admin (auth required):
- `/api/v1/admin/announcements*`
- `/api/v1/admin/events*`
- `/api/v1/admin/resources*`
- `/api/v1/admin/messages*`
- `/api/v1/admin/site-settings*`
- `/api/v1/admin/service-requests*`
- `/api/v1/admin/carousel*`

## CONDO accounting/billing integration possibility

From the CONDO repository review, there are reusable billing primitives and invoice amount-distribution logic (for splitting incoming payments across recipients). In this codebase, the practical integration path is:
- keep current resident UI/API as-is;
- add a backend adapter service that maps GolfMeadows billing records to CONDO invoice/distribution payloads;
- run that adapter behind admin-authenticated routes and webhooks.

This is feasible, but it is a separate integration project (data model + payment provider + reconciliation), not a same-day demo change.

## CONDO integration design notes

The backend is intentionally API-first:

- versioned endpoints under `/api/v1`
- explicit schemas for portability
- separable frontend (can be replaced by CONDO UI while reusing APIs)
- storage abstraction via environment variable

See `docs/condo-integration.md` for integration guidance.
