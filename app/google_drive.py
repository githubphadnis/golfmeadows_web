import re

import requests


FOLDER_ID_PATTERNS = (
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
)
IMAGE_URL_PATTERN = re.compile(r"https://drive\.google\.com/uc\?id=([a-zA-Z0-9_-]+)")
DRIVE_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif")


def extract_google_drive_folder_id(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        return ""
    for pattern in FOLDER_ID_PATTERNS:
        match = pattern.search(candidate)
        if match:
            return match.group(1)
    return ""


def fetch_drive_folder_images(folder_id: str, timeout: int = 8) -> list[str]:
    if not folder_id:
        return []

    embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#grid"
    try:
        response = requests.get(embed_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []

    html = response.text
    image_urls: list[str] = []

    for file_id in IMAGE_URL_PATTERN.findall(html):
        image_urls.append(f"https://drive.google.com/uc?export=view&id={file_id}")

    if image_urls:
        return list(dict.fromkeys(image_urls))

    # Fallback: parse drive file links from markup and accept only image extensions.
    file_id_candidates = re.findall(r"/file/d/([a-zA-Z0-9_-]+)/", html)
    for file_id in file_id_candidates:
        for ext in DRIVE_IMAGE_EXTENSIONS:
            if f".{ext}" in html.lower():
                image_urls.append(f"https://drive.google.com/uc?export=view&id={file_id}")
                break

    return list(dict.fromkeys(image_urls))
