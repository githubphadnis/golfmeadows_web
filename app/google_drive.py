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
        "fields": "files(id,name,mimeType,thumbnailLink,webContentLink,iconLink)",
    }
    try:
        response = requests.get(DRIVE_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []

    payload = response.json()
    return payload.get("files", []) if isinstance(payload, dict) else []


def _normalize_thumbnail(url: str, api_key: str) -> str:
    if not url:
        return ""
    return f"{url}&key={api_key}" if "key=" not in url else url


def _extension_from_name(name: str) -> str:
    if "." not in (name or ""):
        return ""
    return name.rsplit(".", 1)[1].lower()


def fetch_drive_carousel_images(folder_id: str, api_key: str) -> list[str]:
    files = fetch_drive_folder_files(folder_id, api_key)
    images: list[str] = []
    for item in files:
        extension = _extension_from_name(item.get("name", ""))
        if extension in CAROUSEL_EXTENSIONS:
            file_id = item.get("id", "")
            if file_id:
                images.append(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"
                )
    return list(dict.fromkeys(images))


def fetch_drive_documents(folder_id: str, api_key: str) -> list[dict[str, str]]:
    files = fetch_drive_folder_files(folder_id, api_key)
    documents: list[dict[str, str]] = []
    for item in files:
        extension = _extension_from_name(item.get("name", ""))
        if extension not in DOCUMENT_EXTENSIONS:
            continue
        file_id = item.get("id", "")
        if not file_id:
            continue
        download_link = item.get("webContentLink") or (
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"
        )
        documents.append(
            {
                "id": file_id,
                "name": item.get("name", ""),
                "extension": extension,
                "thumbnailLink": _normalize_thumbnail(item.get("thumbnailLink", ""), api_key),
                "webContentLink": download_link,
            }
        )
    return documents
