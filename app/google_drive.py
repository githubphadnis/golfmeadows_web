import re
from typing import Any

import requests


FOLDER_ID_PATTERNS = (
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
)

DRIVE_API_URL = "https://www.googleapis.com/drive/v3/files"
CAROUSEL_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "xlsx", "jpg", "jpeg", "png", "zip"}


def extract_google_drive_folder_id(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        return ""
    for pattern in FOLDER_ID_PATTERNS:
        match = pattern.search(candidate)
        if match:
            return match.group(1)
    return ""


def fetch_drive_folder_files(
    folder_id: str,
    api_key: str,
    *,
    page_size: int = 100,
    timeout: int = 10,
) -> list[dict[str, Any]]:
    if not folder_id or not api_key:
        return []

    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "key": api_key,
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,thumbnailLink,webContentLink,webViewLink,iconLink)",
    }
    response: requests.Response | None = None
    try:
        response = requests.get(DRIVE_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        if response is not None:
            print(f"Drive API Error: {response.status_code} - {response.text}", flush=True)
        else:
            print(f"Drive API Request Error: {exc}", flush=True)
        return []

    payload = response.json()
    files = payload.get("files", []) if isinstance(payload, dict) else []
    if not files:
        print("Drive API returned 0 files. Check folder ID and permissions.", flush=True)
    return files


def _extension_from_name(name: str) -> str:
    if "." not in (name or ""):
        return ""
    return name.rsplit(".", 1)[1].lower()


def _direct_media_link(file_id: str, api_key: str) -> str:
    return f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"


def _web_view_link(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def fetch_drive_carousel_images(folder_id: str, api_key: str) -> list[str]:
    files = fetch_drive_folder_files(folder_id, api_key)
    images: list[str] = []
    for item in files:
        file_id = (item.get("id") or "").strip()
        if not file_id:
            continue
        extension = _extension_from_name(item.get("name", ""))
        mime_type = (item.get("mimeType") or "").lower()
        if extension in CAROUSEL_EXTENSIONS or mime_type.startswith("image/"):
            # Use direct Drive view URL for inline hero rendering.
            images.append(f"https://drive.google.com/uc?export=view&id={file_id}")
    return list(dict.fromkeys(images))


def fetch_drive_documents(folder_id: str, api_key: str) -> list[dict[str, str]]:
    files = fetch_drive_folder_files(folder_id, api_key)
    documents: list[dict[str, str]] = []
    for item in files:
        file_id = (item.get("id") or "").strip()
        if not file_id:
            continue
        name = (item.get("name") or "").strip()
        extension = _extension_from_name(name)
        mime_type = (item.get("mimeType") or "").lower()
        if extension not in DOCUMENT_EXTENSIONS and not mime_type.startswith("image/"):
            continue
        documents.append(
            {
                "file_id": file_id,
                "name": name,
                "extension": extension,
                "thumbnail_link": (item.get("thumbnailLink") or "").strip(),
                "web_content_link": (item.get("webContentLink") or "").strip()
                or _direct_media_link(file_id, api_key),
                "web_view_link": _web_view_link(file_id),
            }
        )
    return documents
