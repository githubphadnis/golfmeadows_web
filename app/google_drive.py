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
    timeout: int = 10,
) -> list[dict[str, Any]]:
    if not folder_id or not api_key:
        return []

    # Requested query shape for folder file fetch.
    query_url = (
        f"{DRIVE_API_URL}"
        f"?q='{folder_id}'+in+parents"
        f"&key={api_key}"
        "&fields=files(id,name,thumbnailLink,webContentLink,mimeType)"
    )
    try:
        response = requests.get(query_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []

    payload = response.json()
    return payload.get("files", []) if isinstance(payload, dict) else []


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
            # Prefer thumbnailLink for fast hero loading, fallback to media link.
            thumb = (item.get("thumbnailLink") or "").strip()
            images.append(thumb or _direct_media_link(file_id, api_key))
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
