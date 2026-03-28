from pathlib import Path
import os


def _resolve_data_dir() -> Path:
    # Keep storage location configurable so it can map to a Docker volume.
    base = os.getenv("GOLFMEADOWS_DATA_DIR", "data")
    path = Path(base).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = _resolve_data_dir()
UPLOADS_DIR = DATA_DIR / "uploads"
CAROUSEL_DIR = UPLOADS_DIR / "carousel"
DB_PATH = DATA_DIR / "golfmeadows.db"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
CAROUSEL_DIR.mkdir(parents=True, exist_ok=True)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@golfmeadows.local").strip()
SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
