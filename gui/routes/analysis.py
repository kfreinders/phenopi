from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from gui.services.analysis_preview import (
    build_analysis_preview,
    build_roi_preview,
)


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_data: str = Field(min_length=1, max_length=13_500_000)
    config: dict = Field(default_factory=dict)


@router.get("/configure")
def configure_analysis() -> dict:
    from scripts.analysis.config import AnalysisConfig

    return {"config": AnalysisConfig().to_dict()}


@router.post("/preview")
def preview_analysis(request: AnalysisPreviewRequest) -> dict:
    try:
        return build_analysis_preview(request.image_data, request.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/roi")
def detect_analysis_roi(request: AnalysisPreviewRequest) -> dict:
    try:
        return build_roi_preview(request.image_data, request.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
