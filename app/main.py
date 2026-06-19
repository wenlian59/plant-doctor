import logging
from datetime import datetime, timezone

from fastapi import FastAPI, File, UploadFile
from pydantic import ValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import classifier, db, llm_client, storage
from app.llm_client import NotAPlantError
from app.schemas import (
    Diagnosis,
    DiagnoseResponse,
    HistoryDetail,
    HistoryDetailResponse,
    HistoryItem,
    HistoryListResponse,
    Identifier,
    PlantResult,
    Schedule,
)

logger = logging.getLogger("plant_doctor")

app = FastAPI(title="Plant Doctor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

app.mount("/uploads", StaticFiles(directory=str(storage.UPLOADS_DIR)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/diagnose", response_model=DiagnoseResponse)
async def diagnose(image: UploadFile = File(...)):
    image_bytes = await image.read()
    if not image_bytes:
        return DiagnoseResponse(success=False, message="unsupported_format")

    if len(image_bytes) > 10 * 1024 * 1024:
        return DiagnoseResponse(success=False, message="image_too_large")

    if (image.content_type or "") not in ("image/jpeg", "image/png", "image/webp"):
        return DiagnoseResponse(success=False, message="unsupported_format")

    try:
        label, confidence = await run_in_threadpool(classifier.classify, image_bytes)
    except Exception:
        return DiagnoseResponse(success=False, message="unsupported_format")

    try:
        result = await llm_client.diagnose(
            image_bytes=image_bytes,
            mime_type=image.content_type or "image/jpeg",
            label=label,
            confidence=confidence,
        )
    except NotAPlantError:
        return DiagnoseResponse(success=False, message="not_a_plant")
    except TimeoutError:
        return DiagnoseResponse(success=False, message="model_timeout")
    except RuntimeError as exc:
        logger.exception("Qwen 诊断失败: %s", exc)
        return DiagnoseResponse(success=False, message="internal_error")

    result["identifier"]["confidence"] = confidence

    try:
        plant_result = PlantResult(
            identifier=Identifier(**result["identifier"]),
            schedule=Schedule(**result["schedule"]),
            diagnosis=Diagnosis(**result["diagnosis"]),
        )
    except ValidationError as exc:
        logger.exception("诊断结果校验失败: %s", exc)
        return DiagnoseResponse(success=False, message="internal_error")

    record_id = storage.new_record_id()
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _persist() -> tuple[str, str]:
        image_url, thumbnail_url = storage.save_image(record_id, image_bytes)
        db.insert_record(
            record_id=record_id,
            created_at=created_at,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            result=plant_result.model_dump(),
        )
        return image_url, thumbnail_url

    await run_in_threadpool(_persist)

    return DiagnoseResponse(success=True, record_id=record_id, data=plant_result)


@app.get("/api/history", response_model=HistoryListResponse)
async def get_history(page: int = 1, limit: int = 10):
    page = max(page, 1)
    limit = min(max(limit, 1), 100)

    total, items = await run_in_threadpool(db.list_records, page, limit)
    return HistoryListResponse(
        success=True,
        total=total,
        page=page,
        limit=limit,
        data=[HistoryItem(**item) for item in items],
    )


@app.get("/api/history/{record_id}", response_model=HistoryDetailResponse)
async def get_history_detail(record_id: str):
    record = await run_in_threadpool(db.get_record, record_id)
    if record is None:
        return HistoryDetailResponse(success=False, message="record_not_found")

    return HistoryDetailResponse(success=True, data=HistoryDetail(**record))


@app.delete("/api/history/{record_id}")
async def delete_history(record_id: str):
    deleted = await run_in_threadpool(db.delete_record, record_id)
    if not deleted:
        return {"success": False, "message": "record_not_found"}

    await run_in_threadpool(storage.delete_image, record_id)
    return {"success": True}
