from typing import Literal

from pydantic import BaseModel


class WeeklySchedule(BaseModel):
    day: str
    water_ml: float | None = None
    sunlight_hours: str = ""


class Treatment(BaseModel):
    title: str
    detail: str


class Identifier(BaseModel):
    common_name: str = ""
    scientific_name: str = ""
    family: str = ""
    confidence: float = 0.0
    about: str = ""
    tags: list[str] = []
    edible_parts: list[str] = []
    common_aliases: list[str] = []


class Schedule(BaseModel):
    soil_type: str = ""
    fertilizer: str = ""
    weekly: list[WeeklySchedule] = []


class Diagnosis(BaseModel):
    health_status: Literal["healthy", "diseased"] = "healthy"
    disease_name: str | None = None
    pathogen: str | None = None
    severity: Literal["low", "moderate", "high"] | None = None
    confidence: float = 0.0
    symptoms: list[str] = []
    treatments: list[Treatment] = []
    prevention: list[str] = []


class PlantResult(BaseModel):
    identifier: Identifier
    schedule: Schedule
    diagnosis: Diagnosis


class DiagnoseResponse(BaseModel):
    success: bool
    record_id: str | None = None
    data: PlantResult | None = None
    message: str | None = None


class HistoryItem(BaseModel):
    record_id: str
    created_at: str
    thumbnail: str
    common_name: str
    scientific_name: str
    health_status: Literal["healthy", "diseased"]
    disease_name: str | None = None


class HistoryListResponse(BaseModel):
    success: bool
    total: int = 0
    page: int = 1
    limit: int = 10
    data: list[HistoryItem] = []
    message: str | None = None


class HistoryDetail(PlantResult):
    record_id: str
    created_at: str
    image_url: str


class HistoryDetailResponse(BaseModel):
    success: bool
    data: HistoryDetail | None = None
    message: str | None = None
