from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gui.config import templates
from gui.services.schedule_preview import (
    build_schedule_preview,
    form_defaults,
    parse_bool_checkbox,
    resolve_output_path,
)
from scripts.scheduling.make_schedule import write_schedule


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
    mode: str = Form(...),
    start_date: str = Form(...),
    num_days: int = Form(...),
    replicates: int = Form(...),
    replicate_interval_seconds: int = Form(...),
    output: str = Form(...),
    overwrite: str | None = Form(None),
    every_start: str = Form("08:00"),
    every_end: str = Form("19:30"),
    every_step_minutes: int = Form(30),
    duration_start: str = Form("08:00"),
    duration_minutes: int = Form(720),
    duration_step_minutes: int = Form(30),
    centered_center: str = Form("12:00"),
    centered_before_minutes: int = Form(60),
    centered_after_minutes: int = Form(60),
    centered_step_minutes: int = Form(15),
) -> HTMLResponse:
    form = _schedule_form_data(
        mode=mode,
        start_date=start_date,
        num_days=num_days,
        replicates=replicates,
        replicate_interval_seconds=replicate_interval_seconds,
        output=output,
        overwrite=overwrite,
        every_start=every_start,
        every_end=every_end,
        every_step_minutes=every_step_minutes,
        duration_start=duration_start,
        duration_minutes=duration_minutes,
        duration_step_minutes=duration_step_minutes,
        centered_center=centered_center,
        centered_before_minutes=centered_before_minutes,
        centered_after_minutes=centered_after_minutes,
        centered_step_minutes=centered_step_minutes,
    )

    try:
        preview = build_schedule_preview(**form)
        error = None
    except Exception as exc:  # noqa: BLE001 - show validation error in GUI
        preview = None
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "request": request,
            "active_tab": "schedule",
            "form": form,
            "preview": preview,
            "message": None,
            "error": error,
        },
    )


@router.post("/schedule/save", response_class=HTMLResponse)
def save_schedule(
    request: Request,
    mode: str = Form(...),
    start_date: str = Form(...),
    num_days: int = Form(...),
    replicates: int = Form(...),
    replicate_interval_seconds: int = Form(...),
    output: str = Form(...),
    overwrite: str | None = Form(None),
    every_start: str = Form("08:00"),
    every_end: str = Form("19:30"),
    every_step_minutes: int = Form(30),
    duration_start: str = Form("08:00"),
    duration_minutes: int = Form(720),
    duration_step_minutes: int = Form(30),
    centered_center: str = Form("12:00"),
    centered_before_minutes: int = Form(60),
    centered_after_minutes: int = Form(60),
    centered_step_minutes: int = Form(15),
) -> HTMLResponse:
    form = _schedule_form_data(
        mode=mode,
        start_date=start_date,
        num_days=num_days,
        replicates=replicates,
        replicate_interval_seconds=replicate_interval_seconds,
        output=output,
        overwrite=overwrite,
        every_start=every_start,
        every_end=every_end,
        every_step_minutes=every_step_minutes,
        duration_start=duration_start,
        duration_minutes=duration_minutes,
        duration_step_minutes=duration_step_minutes,
        centered_center=centered_center,
        centered_before_minutes=centered_before_minutes,
        centered_after_minutes=centered_after_minutes,
        centered_step_minutes=centered_step_minutes,
    )

    try:
        preview = build_schedule_preview(**form)
        output_path = resolve_output_path(preview.output)

        write_schedule(
            output=output_path,
            start_date=preview.start_date,
            num_days=preview.num_days,
            times=preview.times,
            replicates=preview.replicates,
            replicate_interval_seconds=preview.replicate_interval_seconds,
            overwrite=preview.overwrite,
        )

        message = f"Wrote schedule to {output_path}"
        error = None
    except Exception as exc:  # noqa: BLE001 - show validation error in GUI
        preview = None
        message = None
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "request": request,
            "active_tab": "schedule",
            "form": form,
            "preview": preview,
            "message": message,
            "error": error,
        },
    )


def _schedule_form_data(
    *,
    mode: str,
    start_date: str,
    num_days: int,
    replicates: int,
    replicate_interval_seconds: int,
    output: str,
    overwrite: str | None,
    every_start: str,
    every_end: str,
    every_step_minutes: int,
    duration_start: str,
    duration_minutes: int,
    duration_step_minutes: int,
    centered_center: str,
    centered_before_minutes: int,
    centered_after_minutes: int,
    centered_step_minutes: int,
) -> dict:
    return {
        "mode": mode,
        "start_date": start_date,
        "num_days": num_days,
        "replicates": replicates,
        "replicate_interval_seconds": replicate_interval_seconds,
        "output": output,
        "overwrite": parse_bool_checkbox(overwrite),
        "every_start": every_start,
        "every_end": every_end,
        "every_step_minutes": every_step_minutes,
        "duration_start": duration_start,
        "duration_minutes": duration_minutes,
        "duration_step_minutes": duration_step_minutes,
        "centered_center": centered_center,
        "centered_before_minutes": centered_before_minutes,
        "centered_after_minutes": centered_after_minutes,
        "centered_step_minutes": centered_step_minutes,
    }
