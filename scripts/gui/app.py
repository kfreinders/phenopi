from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from scripts.scheduling.make_schedule import (
    centered_time_range,
    every_n_minutes,
    every_n_minutes_for_duration,
    validate_unique_expanded_times,
    write_schedule,
)

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[2]
DEFAULT_SCHEDULE_PATH = PROJECT_ROOT / "runtime" / "schedule.json"

app = FastAPI(title="Phenopi GUI")
app.mount(
    "/static",
    StaticFiles(directory=APP_DIR / "static"),
    name="static",
)
templates = Jinja2Templates(directory=APP_DIR / "templates")


@dataclass
class SchedulePreview:
    mode: str
    start_date: str
    num_days: int
    times: list[str]
    replicates: int
    replicate_interval_seconds: int
    output: str
    overwrite: bool

    @property
    def daily_time_points(self) -> int:
        return len(self.times)

    @property
    def daily_captures(self) -> int:
        return self.daily_time_points * self.replicates

    @property
    def total_captures(self) -> int:
        return self.daily_captures * self.num_days

    @property
    def first_time(self) -> str:
        return self.times[0] if self.times else "—"

    @property
    def last_time(self) -> str:
        return self.times[-1] if self.times else "—"

    def as_schedule_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "num_days": self.num_days,
            "replicates": self.replicates,
            "replicate_interval_seconds": self.replicate_interval_seconds,
            "times": self.times,
        }


def parse_bool_checkbox(value: str | None) -> bool:
    return value == "on"


def resolve_output_path(output: str) -> Path:
    path = Path(output).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def build_schedule_preview(
    *,
    mode: str,
    start_date: str,
    num_days: int,
    replicates: int,
    replicate_interval_seconds: int,
    output: str,
    overwrite: bool,
    every_start: str | None = None,
    every_end: str | None = None,
    every_step_minutes: int | None = None,
    duration_start: str | None = None,
    duration_minutes: int | None = None,
    duration_step_minutes: int | None = None,
    centered_center: str | None = None,
    centered_before_minutes: int | None = None,
    centered_after_minutes: int | None = None,
    centered_step_minutes: int | None = None,
) -> SchedulePreview:
    if num_days <= 0:
        raise ValueError("Number of days must be greater than 0.")
    if replicates <= 0:
        raise ValueError("Replicates must be greater than 0.")
    if replicate_interval_seconds < 0:
        raise ValueError("Replicate interval must be 0 or greater.")

    if mode == "every":
        if every_start is None or every_end is None or every_step_minutes is None:
            raise ValueError("Every mode requires start, end, and step minutes.")
        times = every_n_minutes(every_start, every_end, every_step_minutes)
    elif mode == "duration":
        if duration_start is None or duration_minutes is None or duration_step_minutes is None:
            raise ValueError("Duration mode requires start, duration, and step minutes.")
        times = every_n_minutes_for_duration(
            duration_start,
            duration_minutes,
            duration_step_minutes,
        )
    elif mode == "centered":
        if (
            centered_center is None
            or centered_before_minutes is None
            or centered_after_minutes is None
            or centered_step_minutes is None
        ):
            raise ValueError("Centered mode requires center, before, after, and step minutes.")
        times = centered_time_range(
            centered_center,
            centered_before_minutes,
            centered_after_minutes,
            centered_step_minutes,
        )
    else:
        raise ValueError(f"Unknown schedule mode: {mode!r}.")

    validate_unique_expanded_times(
        times=times,
        replicates=replicates,
        replicate_interval_seconds=replicate_interval_seconds,
    )

    return SchedulePreview(
        mode=mode,
        start_date=start_date,
        num_days=num_days,
        times=times,
        replicates=replicates,
        replicate_interval_seconds=replicate_interval_seconds,
        output=output,
        overwrite=overwrite,
    )


def form_defaults() -> dict[str, Any]:
    return {
        "mode": "every",
        "start_date": "",
        "num_days": 14,
        "replicates": 3,
        "replicate_interval_seconds": 30,
        "output": str(DEFAULT_SCHEDULE_PATH.relative_to(PROJECT_ROOT)),
        "overwrite": True,
        "every_start": "08:00",
        "every_end": "19:30",
        "every_step_minutes": 30,
        "duration_start": "08:00",
        "duration_minutes": 720,
        "duration_step_minutes": 30,
        "centered_center": "12:00",
        "centered_before_minutes": 60,
        "centered_after_minutes": 60,
        "centered_step_minutes": 15,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/schedule", status_code=303)


@app.get("/schedule", response_class=HTMLResponse)
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


@app.post("/schedule/preview", response_class=HTMLResponse)
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
    form = {
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

    try:
        preview = build_schedule_preview(**form)
        error = None
    except Exception as exc:  # noqa: BLE001 - show validation error in GUI.
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


@app.post("/schedule/save", response_class=HTMLResponse)
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
    form = {
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
    except Exception as exc:  # noqa: BLE001 - show validation error in GUI.
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


def main() -> None:

    uvicorn.run(
        "scripts.gui.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
