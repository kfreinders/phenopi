from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gui.config import templates
from gui.services.schedule_preview import (
    ScheduleFormData,
    build_schedule_preview,
    form_defaults,
    save_schedule_preview,
)


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/schedule", status_code=303)


@router.get("/schedule", response_class=HTMLResponse)
def schedule_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "request": request,
            "active_tab": "schedule",
            "form": form_defaults(),
            "preview": None,
            "message": None,
            "error": None,
        },
    )


@router.post("/schedule/preview", response_class=HTMLResponse)
def preview_schedule(
    request: Request,
    form: Annotated[ScheduleFormData, Form()],
) -> HTMLResponse:
    return _process_schedule_form(request, form, save=False)


@router.post("/schedule/save", response_class=HTMLResponse)
def save_schedule(
    request: Request,
    form: Annotated[ScheduleFormData, Form()],
) -> HTMLResponse:
    return _process_schedule_form(request, form, save=True)


def _process_schedule_form(
    request: Request,
    form: ScheduleFormData,
    *,
    save: bool,
) -> HTMLResponse:
    form_data = form.preview_arguments()
    try:
        preview = build_schedule_preview(**form_data)
        output_path = save_schedule_preview(preview) if save else None
        message = f"Wrote schedule to {output_path}" if output_path else None
        error = None
    except (OSError, ValueError) as exc:
        preview = None
        message = None
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "request": request,
            "active_tab": "schedule",
            "form": form_data,
            "preview": preview,
            "message": message,
            "error": error,
        },
    )
