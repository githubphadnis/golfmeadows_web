from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps


def process_image_for_carousel(raw_bytes: bytes, output_dir: Path) -> tuple[str, Path]:
    """
    Normalize orientation, resize for web, and compress to WebP.
    Returns generated filename and absolute saved path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(BytesIO(raw_bytes)) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        # Fit into 1920x1080 while preserving aspect ratio.
        normalized.thumbnail((1920, 1080))

        filename = f"{uuid4().hex}.webp"
        save_path = output_dir / filename
        normalized.save(save_path, format="WEBP", quality=82, method=6)
        return filename, save_path
