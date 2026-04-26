import re
from typing import Any

import requests
from flask import has_request_context, request


FOLDER_ID_PATTERNS = (
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
)

DRIVE_API_URL = "https://www.googleapis.com/drive/v3/files"
CAROUSEL_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "xlsx", "jpg", "jpeg", "png", "zip"}


def _drive_request_headers() -> dict[str, str]:
    if not has_request_context():
        return {}

    host_origin = request.host_url.rstrip("/")
    incoming_referer = (request.headers.get("Referer") or "").strip()
    referer = incoming_referer or host_origin

    headers: dict[str, str] = {"Referer": referer}
    if host_origin:
        headers["Origin"] = host_origin
    return headers


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
) -> tuple[list[dict[str, Any]], bool]:
    if not folder_id or not api_key:
        return [], True

    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "key": api_key,
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,thumbnailLink,webContentLink,webViewLink,iconLink)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    headers = _drive_request_headers()
    response: requests.Response | None = None
    try:
        response = requests.get(DRIVE_API_URL, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        if response is not None:
            print(f"Drive API Error: {response.status_code} - {response.text}", flush=True)
        else:
            print(f"Drive API Request Error: {exc}", flush=True)
        return [], True

    payload = response.json()
    files = payload.get("files", []) if isinstance(payload, dict) else []
    if not files:
        print("Drive API returned 0 files. Check folder ID and permissions.", flush=True)
    return files, False


def _extension_from_name(name: str) -> str:
    if "." not in (name or ""):
        return ""
    return name.rsplit(".", 1)[1].lower()


def _direct_media_link(file_id: str, api_key: str) -> str:
    return f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"


def _web_view_link(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def fetch_drive_carousel_images(folder_id: str, api_key: str) -> list[dict[str, str]]:
    files, _ = fetch_drive_folder_files(folder_id, api_key)
    images: list[dict[str, str]] = []
    for item in files:
        file_id = (item.get("id") or "").strip()
        if not file_id:
            continue
        extension = _extension_from_name(item.get("name", ""))
        mime_type = (item.get("mimeType") or "").lower()
        if extension in CAROUSEL_EXTENSIONS or mime_type.startswith("image/"):
            images.append(
                {
                    "id": file_id,
                    "name": (item.get("name") or "").strip(),
                }
            )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for image in images:
        file_id = image.get("id", "")
        if file_id and file_id not in seen:
            deduped.append(image)
            seen.add(file_id)
    return deduped


def fetch_drive_documents(folder_id: str, api_key: str) -> tuple[list[dict[str, str]], bool]:
    files, had_error = fetch_drive_folder_files(folder_id, api_key)
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
    return documents, had_error
