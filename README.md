# GolfMeadows Community Portal

Full-stack website for **GolfMeadows Housing Society (Panvel, Maharashtra)** with:

- modern public landing page and dynamic content sections
- optimized carousel uploads (server-side resize/compress)
- persistent storage for media and data
- positive **Service Requests** workflow (instead of complaints)
- admin console for announcements, events, resources, messages, and request operations
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

Behavior:

1. On push to `main` (and active feature branch), build and push image to GHCR:
   - `ghcr.io/<owner>/<repo>:latest`
   - `ghcr.io/<owner>/<repo>:sha-<shortsha>`
2. On **Release Published** (or manual workflow dispatch), trigger Portainer webhook if configured.

### Required repository settings and secrets

- Repository **Actions permissions** must allow write to packages.
- `PORTAINER_WEBHOOK_URL` (required for release-driven auto-redeploy)

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

### Push this branch to `main`

The CI workflow runs on `main`, so merge this branch into `main` to activate automated build/deploy.

## Cloudflare Tunnel test plan

Use `deployment/cloudflared-config.example.yml` as template.

Validate:

- `https://<your-domain>/` -> public homepage
- `https://<your-domain>/admin.html` -> admin page
- `https://<your-domain>/api/health` -> `{"status":"ok", ...}`
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
- configure recipient email lists for service requests and feedback from Admin
- view response/resolution SLA due timestamps and breach flags

## Email notifications (Phase 1)

Configured via environment variables:

```bash
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=no-reply@golfmeadows.local
SMTP_USE_TLS=true
```

Notification flow:

- on service request create/update/timeline update -> send to configured service request recipients
- on feedback message create -> send to configured feedback recipients
- notification outcomes are logged in notification audit (`/api/v1/admin/notification-audit`)

## CONDO integration design notes

The backend is intentionally API-first:

- versioned endpoints under `/api/v1`
- explicit schemas for portability
- separable frontend (can be replaced by CONDO UI while reusing APIs)
- storage abstraction via environment variable

See `docs/condo-integration.md` for integration guidance.
