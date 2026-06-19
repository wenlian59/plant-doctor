import random
import string
import time
from io import BytesIO

from PIL import Image

from app.config import BASE_DIR

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

THUMBNAIL_SIZE = (200, 200)

_RANDOM_CHARS = string.ascii_lowercase + string.digits


def new_record_id() -> str:
    suffix = "".join(random.choices(_RANDOM_CHARS, k=3))
    return f"rec_{int(time.time() * 1000)}_{suffix}"


def save_image(record_id: str, image_bytes: bytes) -> tuple[str, str]:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

    image_path = UPLOADS_DIR / f"{record_id}.jpg"
    image.save(image_path, "JPEG", quality=90)

    thumb = image.copy()
    thumb.thumbnail(THUMBNAIL_SIZE)
    thumb_path = UPLOADS_DIR / f"thumb_{record_id}.jpg"
    thumb.save(thumb_path, "JPEG", quality=85)

    return f"/uploads/{record_id}.jpg", f"/uploads/thumb_{record_id}.jpg"


def delete_image(record_id: str) -> None:
    (UPLOADS_DIR / f"{record_id}.jpg").unlink(missing_ok=True)
    (UPLOADS_DIR / f"thumb_{record_id}.jpg").unlink(missing_ok=True)
