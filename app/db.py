import json
import threading

from app.config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
HISTORY_PATH = DATA_DIR / "history.json"

_lock = threading.Lock()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_PATH.exists():
        HISTORY_PATH.write_text("[]", encoding="utf-8")


def _read_all() -> list[dict]:
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_all(records: list[dict]) -> None:
    HISTORY_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def insert_record(record_id: str, created_at: str, image_url: str, thumbnail_url: str, result: dict) -> None:
    record = {
        "record_id": record_id,
        "created_at": created_at,
        "image_url": image_url,
        "thumbnail": thumbnail_url,
        **result,
    }
    with _lock:
        records = _read_all()
        records.insert(0, record)
        _write_all(records)


def list_records(page: int, limit: int) -> tuple[int, list[dict]]:
    with _lock:
        records = _read_all()

    total = len(records)
    offset = (page - 1) * limit
    page_records = records[offset:offset + limit]

    items = [
        {
            "record_id": r["record_id"],
            "created_at": r["created_at"],
            "thumbnail": r["thumbnail"],
            "common_name": r["identifier"].get("common_name", ""),
            "scientific_name": r["identifier"].get("scientific_name", ""),
            "health_status": r["diagnosis"].get("health_status", "healthy"),
            "disease_name": r["diagnosis"].get("disease_name"),
        }
        for r in page_records
    ]
    return total, items


def get_record(record_id: str) -> dict | None:
    with _lock:
        records = _read_all()

    for r in records:
        if r["record_id"] == record_id:
            return {
                "record_id": r["record_id"],
                "created_at": r["created_at"],
                "image_url": r["image_url"],
                "identifier": r["identifier"],
                "schedule": r["schedule"],
                "diagnosis": r["diagnosis"],
            }
    return None


def delete_record(record_id: str) -> bool:
    with _lock:
        records = _read_all()
        remaining = [r for r in records if r["record_id"] != record_id]
        if len(remaining) == len(records):
            return False
        _write_all(remaining)
    return True
