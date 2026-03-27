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
data/
  golfmeadows.db     # SQLite DB (created at runtime)
  uploads/carousel/  # Optimized uploaded images
```

## Run locally

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Start the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4173
```

3. Open:

- Public site: `http://127.0.0.1:4173/`
- Admin site: `http://127.0.0.1:4173/admin.html`
- API docs: `http://127.0.0.1:4173/docs`

## Persistent volume location

By default, data is stored in `./data`.

To mount to a different volume/location, set:

```bash
export GOLFMEADOWS_DATA_DIR=/path/to/volume
```

## Service Requests lifecycle

Residents can submit service requests and track them via ticket refs (`GM-SR-00001`).
Admin can:

- update status (`Submitted`, `In Review`, `In Progress`, `Resolved`, `Closed`)
- add internal notes
- append timeline updates (activities)

## CONDO integration design notes

The backend is intentionally API-first:

- versioned endpoints under `/api/v1`
- explicit schemas for portability
- separable frontend (can be replaced by CONDO UI while reusing APIs)
- storage abstraction via environment variable

See `docs/condo-integration.md` for integration guidance.
