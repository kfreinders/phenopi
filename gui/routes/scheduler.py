from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from gui.config import (
    SCHEDULE_DRAFT_PATH,
    SCHEDULER_COMMAND_PATH,
    SCHEDULER_HEARTBEAT_PATH,
)
from gui.services.schedule_drafts import load_current_schedule_draft
from gui.services.scheduler_status import (
    read_scheduler_health,
    read_scheduler_status,
)
from scripts.scheduling.commands import (
    read_schedule_cancellation,
    request_schedule_cancellation,
)


router = APIRouter()


class CancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_hash: str


def schedule_draft_state() -> str:
    """Return the scheduler-page action state for the persisted draft."""
    try:
        draft = load_current_schedule_draft(SCHEDULE_DRAFT_PATH)
    except ValueError:
        return "invalid"
    return "ready" if draft is not None else "none"


@router.get("/api/scheduler/status")
def scheduler_status_api() -> dict:
    status = read_scheduler_status(SCHEDULER_HEARTBEAT_PATH)
    schedule_hash = (status.get("schedule") or {}).get("hash")
    return {
        **status,
        "draft_state": schedule_draft_state(),
        "cancellation_pending": _cancellation_pending(schedule_hash),
    }


@router.post("/api/scheduler/cancel", status_code=202)
def cancel_scheduled_experiment(request: CancellationRequest) -> dict:
    status = read_scheduler_status(SCHEDULER_HEARTBEAT_PATH)
    scheduled = status.get("schedule")
    if status["status"] in {"stale", "unavailable"}:
        raise HTTPException(
            status_code=503,
            detail="The scheduler is not responding. The experiment cannot be stopped safely.",
        )
    if not scheduled or scheduled.get("lifecycle") not in {"active", "upcoming"}:
        raise HTTPException(
            status_code=409,
            detail="No active or upcoming experiment can be cancelled.",
        )
    if scheduled.get("hash") != request.schedule_hash:
        raise HTTPException(
            status_code=409,
            detail="The active schedule changed. Refresh before stopping the experiment.",
        )
    try:
        request_schedule_cancellation(SCHEDULER_COMMAND_PATH, request.schedule_hash)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="The cancellation request could not be saved.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": True, "schedule_hash": request.schedule_hash}


def _cancellation_pending(schedule_hash: str | None) -> bool:
    try:
        request = read_schedule_cancellation(SCHEDULER_COMMAND_PATH)
    except ValueError:
        return False
    return bool(request and request.schedule_hash == schedule_hash)


@router.get("/api/scheduler/health")
def scheduler_health_api() -> dict:
    return read_scheduler_health(SCHEDULER_HEARTBEAT_PATH)
