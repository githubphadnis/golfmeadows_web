import os
from pathlib import Path


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    DB_PATH = Path(os.getenv("DATABASE_PATH", "/app/data/db/society.db")).resolve()
    UPLOADS_PATH = Path(os.getenv("UPLOADS_PATH", "/app/data/uploads")).resolve()
    SOCIETY_NAME = os.getenv("SOCIETY_NAME", "Cooperative Housing Society").strip()

    GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "").strip()
    SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "").strip().lower()

    GOOGLE_DRIVE_API_KEY = os.getenv("GOOGLE_DRIVE_API_KEY", "").strip()
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    GOOGLE_DRIVE_FOLDER_URL = os.getenv("GOOGLE_DRIVE_FOLDER_URL", "").strip()
    ALLOWED_UPLOAD_EXTENSIONS = {
        "pdf",
        "docx",
        "xlsx",
        "jpg",
        "jpeg",
        "png",
        "zip",
    }

    DEFAULT_CAROUSEL_IMAGES: list[dict[str, str]] = []

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.DB_PATH}"
