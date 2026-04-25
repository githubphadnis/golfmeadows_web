import re
from pathlib import Path
from urllib.parse import quote_plus
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    candidate = (email or "").strip().lower()
    if not candidate:
        return ""
    return candidate if EMAIL_RE.fullmatch(candidate) else ""


def build_email_links(to_email: str, subject: str, body: str) -> dict:
    to_encoded = quote_plus(to_email)
    subject_encoded = quote_plus(subject)
    body_encoded = quote_plus(body)
    return {
        "mailto": f"mailto:{to_email}?subject={subject_encoded}&body={body_encoded}",
        "gmail": (
            "https://mail.google.com/mail/?view=cm&fs=1"
            f"&to={to_encoded}&su={subject_encoded}&body={body_encoded}"
        ),
    }


def ensure_storage_directories(config_obj: dict) -> None:
    Path(config_obj["DB_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(config_obj["UPLOADS_PATH"]).mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in allowed_extensions


def save_uploaded_file(file: FileStorage, uploads_root: Path) -> tuple[str, str, str]:
    safe_name = secure_filename(file.filename or "")
    extension = safe_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid4().hex}_{safe_name}"
    destination = uploads_root / stored_name
    file.save(destination)
    return stored_name, stored_name, extension


def file_icon_for_extension(ext: str) -> str:
    mapping = {
        "pdf": "📄",
        "docx": "📝",
        "xlsx": "📊",
        "jpg": "🖼️",
        "jpeg": "🖼️",
        "png": "🖼️",
        "zip": "🗜️",
    }
    return mapping.get((ext or "").lower(), "📁")
