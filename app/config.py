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
