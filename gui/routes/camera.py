from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gui.config import templates


router = APIRouter()


@router.get("/camera", response_class=HTMLResponse)
def camera_preview(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "camera.html",
        {
            "request": request,
            "active_tab": "camera",
        },
    )
