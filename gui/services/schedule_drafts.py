from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from phenopi.config import DEFAULT_SCHEDULE_PATH, SCHEDULE_DRAFT_PATH
from gui.services.schedule_builder import (
    PastStartDateError,
    SchedulePreview,
    build_schedule_preview,
)
from gui.services.schedule_form import ScheduleFormData
from scripts.scheduling.make_schedule import (
    atomic_write_text,
    schedule_json,
    write_schedule,
)


DRAFT_VERSION = 2


class ScheduleDraft(BaseModel):
    """A persisted, reviewed schedule and the form that generated it."""

    version: int = DRAFT_VERSION
    created_at: str
    form: ScheduleFormData
    schedule: dict[str, Any]
    schedule_hash: str


def persist_schedule_draft(
    form: ScheduleFormData,
    path: Path = SCHEDULE_DRAFT_PATH,
) -> ScheduleDraft:
    preview = build_schedule_preview(**form.preview_arguments())
    run = {
        "id": str(uuid4()),
        "name": form.experiment_name,
        "researcher": form.researcher,
        "notes": form.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    schedule = {**preview.as_schedule_dict(), "run": run}
    draft = ScheduleDraft(
        created_at=datetime.now(timezone.utc).isoformat(),
        form=form,
        schedule=schedule,
        schedule_hash=_schedule_hash(schedule),
    )
    atomic_write_text(path, draft.model_dump_json(indent=2) + "\n")
    return draft


def load_schedule_draft(
    path: Path = SCHEDULE_DRAFT_PATH,
) -> tuple[ScheduleDraft, SchedulePreview]:
    try:
        draft = ScheduleDraft.model_validate_json(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("The saved schedule draft could not be read.") from exc
    if draft.version != DRAFT_VERSION:
        raise ValueError("The saved schedule draft uses an unsupported version.")
    preview = build_schedule_preview(**draft.form.preview_arguments())
    expected_schedule = {
        **preview.as_schedule_dict(),
        "run": draft.schedule.get("run"),
    }
    if expected_schedule != draft.schedule:
        raise ValueError("The saved schedule draft is inconsistent.")
    if _schedule_hash(draft.schedule) != draft.schedule_hash:
        raise ValueError("The saved schedule draft has changed unexpectedly.")
    return draft, preview


def load_current_schedule_draft(
    path: Path = SCHEDULE_DRAFT_PATH,
) -> tuple[ScheduleDraft, SchedulePreview] | None:
    """Load a usable draft, removing it if its start date has expired."""
    if not path.exists():
        return None
    try:
        return load_schedule_draft(path)
    except PastStartDateError:
        discard_schedule_draft(path)
        return None


def discard_schedule_draft(path: Path = SCHEDULE_DRAFT_PATH) -> None:
    path.unlink(missing_ok=True)


def activate_schedule_draft(
    expected_hash: str,
    *,
    draft_path: Path = SCHEDULE_DRAFT_PATH,
    schedule_path: Path = DEFAULT_SCHEDULE_PATH,
) -> str:
    draft, preview = load_schedule_draft(draft_path)
    if draft.schedule_hash != expected_hash:
        raise ValueError(
            "This draft has been replaced. Review the latest draft before activating it."
        )
    write_schedule(
        output=schedule_path,
        start_date=preview.start_date,
        num_days=preview.num_days,
        times=preview.times,
        replicates=preview.replicates,
        replicate_interval_seconds=preview.replicate_interval_seconds,
        run=draft.schedule["run"],
        overwrite=True,
    )
    discard_schedule_draft(draft_path)
    return draft.schedule_hash


def _schedule_hash(schedule: dict[str, Any]) -> str:
    return hashlib.sha256(schedule_json(schedule).encode()).hexdigest()
