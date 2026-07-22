from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gui.config import (
    SCHEDULE_DRAFT_PATH,
    SCHEDULER_HEARTBEAT_PATH,
    templates,
)
from gui.services.schedule_drafts import load_current_schedule_draft
from gui.services.scheduler_status import (
    read_scheduler_health,
    read_scheduler_status,
)


router = APIRouter()


def schedule_draft_state() -> str:
    """Return the scheduler-page action state for the persisted draft."""
    try:
        draft = load_current_schedule_draft(SCHEDULE_DRAFT_PATH)
    except ValueError:
        return "invalid"
    return "ready" if draft is not None else "none"


@router.get("/scheduler", response_class=HTMLResponse)
def scheduler_status_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "scheduler.html",
        {
            "request": request,
            "active_tab": "scheduler",
            "scheduler_status": read_scheduler_status(
                SCHEDULER_HEARTBEAT_PATH
            ),
            "schedule_draft_state": schedule_draft_state(),
        },
    )


@router.get("/api/scheduler/status")
def scheduler_status_api() -> dict:
    return read_scheduler_status(SCHEDULER_HEARTBEAT_PATH)


@router.get("/api/scheduler/health")
def scheduler_health_api() -> dict:
    return read_scheduler_health(SCHEDULER_HEARTBEAT_PATH)
