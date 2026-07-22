from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gui.config import (
    DEFAULT_SCHEDULE_PATH,
    SCHEDULE_DRAFT_PATH,
    SCHEDULER_HEARTBEAT_PATH,
    templates,
)
from gui.services.schedule_preview import (
    ScheduleFormData,
    activate_schedule_draft,
    compare_schedules,
    discard_schedule_draft,
    form_defaults,
    load_schedule_draft,
    persist_schedule_draft,
)
from gui.services.scheduler_status import read_scheduler_status


router = APIRouter()
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@router.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/scheduler", status_code=303)


@router.get("/schedule", response_class=HTMLResponse)
def schedule_form(request: Request) -> HTMLResponse:
    if SCHEDULE_DRAFT_PATH.exists():
        try:
            load_schedule_draft(SCHEDULE_DRAFT_PATH)
        except ValueError as exc:
            return _render_form(request, form_defaults(), error=str(exc))
        return RedirectResponse(url="/schedule/review", status_code=303)
    return _render_form(request, form_defaults())


@router.get("/schedule/edit", response_class=HTMLResponse)
def edit_schedule_draft(request: Request) -> HTMLResponse:
    try:
        draft, _ = load_schedule_draft(SCHEDULE_DRAFT_PATH)
    except ValueError:
        return RedirectResponse(url="/schedule", status_code=303)
    return _render_form(request, draft.form.preview_arguments())


@router.post("/schedule/preview", response_class=HTMLResponse)
def preview_schedule(
    request: Request,
    form: Annotated[ScheduleFormData, Form()],
) -> HTMLResponse:
    try:
        persist_schedule_draft(form, SCHEDULE_DRAFT_PATH)
    except (OSError, ValueError) as exc:
        return _render_form(
            request,
            form.preview_arguments(),
            error=str(exc),
        )
    return RedirectResponse(url="/schedule/review", status_code=303)


@router.get("/schedule/review", response_class=HTMLResponse)
def review_schedule(request: Request) -> HTMLResponse:
    try:
        draft, preview = load_schedule_draft(SCHEDULE_DRAFT_PATH)
    except ValueError as exc:
        return _render_form(request, form_defaults(), error=str(exc))
    status = read_scheduler_status(SCHEDULER_HEARTBEAT_PATH)
    return templates.TemplateResponse(
        request,
        "schedule_review.html",
        _review_context(draft, preview, status),
    )


@router.post("/schedule/draft/discard")
def discard_draft() -> RedirectResponse:
    discard_schedule_draft(SCHEDULE_DRAFT_PATH)
    return RedirectResponse(url="/schedule", status_code=303)


@router.post("/schedule/activate", response_class=HTMLResponse)
def activate_schedule(
    request: Request,
    draft_hash: Annotated[str, Form()],
    confirm_active_replacement: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    try:
        draft, preview = load_schedule_draft(SCHEDULE_DRAFT_PATH)
    except ValueError as exc:
        return _render_form(request, form_defaults(), error=str(exc))
    status = read_scheduler_status(SCHEDULER_HEARTBEAT_PATH)
    context = _review_context(draft, preview, status)

    if draft.schedule_hash != draft_hash:
        context["error"] = (
            "This draft has been replaced. Review the latest draft before activating it."
        )
        return templates.TemplateResponse(request, "schedule_review.html", context)
    if status["status"] in {"stale", "unavailable"}:
        context["error"] = (
            "The scheduler is not responding. Activation is blocked until "
            "it can confirm the new schedule."
        )
        return templates.TemplateResponse(request, "schedule_review.html", context)

    active_schedule = status.get("schedule")
    if active_schedule and active_schedule.get("hash") == draft.schedule_hash:
        discard_schedule_draft(SCHEDULE_DRAFT_PATH)
        return RedirectResponse(
            url=f"/schedule/activation?schedule_hash={draft.schedule_hash}",
            status_code=303,
        )
    replacing_active = bool(
        active_schedule and active_schedule.get("lifecycle") == "active"
    )
    if replacing_active and confirm_active_replacement != "on":
        context["requires_replacement_confirmation"] = True
        context["current_step"] = 3
        return templates.TemplateResponse(request, "schedule_review.html", context)

    try:
        activated_hash = activate_schedule_draft(
            draft_hash,
            draft_path=SCHEDULE_DRAFT_PATH,
            schedule_path=DEFAULT_SCHEDULE_PATH,
        )
    except (OSError, ValueError) as exc:
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "schedule_review.html", context)
    return RedirectResponse(
        url=f"/schedule/activation?schedule_hash={activated_hash}",
        status_code=303,
    )


@router.get("/schedule/activation", response_class=HTMLResponse)
def schedule_activation(
    request: Request,
    schedule_hash: str,
) -> HTMLResponse:
    if not _HASH_PATTERN.fullmatch(schedule_hash):
        return RedirectResponse(url="/schedule", status_code=303)
    status = read_scheduler_status(SCHEDULER_HEARTBEAT_PATH)
    confirmed = (status.get("schedule") or {}).get("hash") == schedule_hash
    return templates.TemplateResponse(
        request,
        "schedule_activation.html",
        {
            "request": request,
            "active_tab": "schedule",
            "current_step": 5 if confirmed else 3,
            "expected_hash": schedule_hash,
            "scheduler_status": status,
            "confirmed": confirmed,
        },
    )


def _render_form(
    request: Request,
    form: dict,
    *,
    error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "request": request,
            "active_tab": "schedule",
            "current_step": 1,
            "form": form,
            "error": error,
        },
    )


def _review_context(draft, preview, status: dict) -> dict:
    active_schedule = status.get("schedule")
    return {
        "active_tab": "schedule",
        "current_step": 2,
        "draft": draft,
        "preview": preview,
        "comparison": compare_schedules(preview, active_schedule),
        "scheduler_status": status,
        "can_activate": status["status"] not in {"stale", "unavailable"},
        "already_active": bool(
            active_schedule
            and active_schedule.get("hash") == draft.schedule_hash
        ),
        "replacing_active": bool(
            active_schedule and active_schedule.get("lifecycle") == "active"
        ),
        "requires_replacement_confirmation": False,
        "error": None,
    }
