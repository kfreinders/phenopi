from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, field_validator

from gui.config import DEFAULT_SCHEDULE_PATH, SCHEDULE_DRAFT_PATH
from scripts.scheduling.make_schedule import (
    atomic_write_text,
    centered_time_range,
    every_n_minutes,
    every_n_minutes_for_duration,
    schedule_json,
    validate_unique_expanded_times,
    write_schedule,
)
from scripts.scheduling.schedule_validation import validate_schedule_size


DRAFT_VERSION = 2


class PastStartDateError(ValueError):
    """Raised when a schedule's start date has already passed."""


class ScheduleFormData(BaseModel):
    """Typed representation of the schedule builder's submitted fields."""

    mode: str
    experiment_name: str
    researcher: str | None = None
    notes: str | None = None
    start_date: str
    num_days: int
    replicates: int
    replicate_interval_seconds: int
    every_start: str = "08:00"
    every_end: str = "19:30"
    every_step_minutes: int = 30
    duration_start: str = "08:00"
    duration_minutes: int = 720
    duration_step_minutes: int = 30
    centered_center: str = "12:00"
    centered_before_minutes: int = 60
    centered_after_minutes: int = 60
    centered_step_minutes: int = 15

    def preview_arguments(self) -> dict[str, Any]:
        return self.model_dump(
            exclude={"experiment_name", "researcher", "notes"}
        )

    def form_arguments(self) -> dict[str, Any]:
        return self.model_dump()

    @field_validator("experiment_name")
    @classmethod
    def validate_experiment_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Experiment name is required.")
        if len(value) > 80:
            raise ValueError("Experiment name must be 80 characters or fewer.")
        return value

    @field_validator("researcher", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        limit = 80 if info.field_name == "researcher" else 1000
        if len(value) > limit:
            label = "Researcher" if info.field_name == "researcher" else "Notes"
            raise ValueError(f"{label} must be {limit} characters or fewer.")
        return value


@dataclass
class SchedulePreview:
    mode: str
    start_date: str
    num_days: int
    times: list[str]
    replicates: int
    replicate_interval_seconds: int

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

    @property
    def end_date(self) -> str:
        start = date.fromisoformat(self.start_date)
        end = start + timedelta(days=self.num_days - 1)
        return end.isoformat()

    @property
    def date_range_label(self) -> str:
        if self.num_days == 1:
            return self.start_date

        return f"{self.start_date} → {self.end_date}"

    @property
    def summary_sentence(self) -> str:
        time_point_word = "time point" if self.daily_time_points == 1 else "time points"
        replicate_word = "replicate" if self.replicates == 1 else "replicates"

        return (
            f"Phenopi will capture {self.daily_captures} images per day "
            f"across {self.daily_time_points} {time_point_word}, with "
            f"{self.replicates} technical {replicate_word} per time point."
        )

    @property
    def replicate_offsets(self) -> list[dict[str, int]]:
        return [
            {
                "number": index + 1,
                "offset_seconds": index * self.replicate_interval_seconds,
            }
            for index in range(self.replicates)
        ]

    @property
    def timeline_points(self) -> list[dict[str, float | str]]:
        if not self.times:
            return []

        start_minutes = _time_to_minutes(self.times[0])
        end_minutes = _time_to_minutes(self.times[-1])
        span = max(end_minutes - start_minutes, 1)

        return [
            {
                "time": time,
                "percent": round(
                    ((_time_to_minutes(time) - start_minutes) / span) * 100,
                    3,
                ),
            }
            for time in self.times
        ]

    def as_schedule_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "num_days": self.num_days,
            "replicates": self.replicates,
            "replicate_interval_seconds": self.replicate_interval_seconds,
            "times": self.times,
        }


def form_defaults() -> dict[str, Any]:
    return {
        "mode": "every",
        "experiment_name": "",
        "researcher": "",
        "notes": "",
        "start_date": date.today().isoformat(),
        "num_days": 14,
        "replicates": 3,
        "replicate_interval_seconds": 30,
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


class ScheduleDraft(BaseModel):
    """A persisted, reviewed schedule and the form that generated it."""

    version: int = DRAFT_VERSION
    created_at: str
    form: ScheduleFormData
    schedule: dict[str, Any]
    schedule_hash: str


@dataclass(frozen=True)
class ScheduleComparison:
    rows: list[dict[str, Any]]
    has_active_schedule: bool
    changed: bool


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


def compare_schedules(
    preview: SchedulePreview,
    active: dict[str, Any] | None,
) -> ScheduleComparison:
    active_range = None
    if active:
        active_range = active["start_date"]
        if active["num_days"] != 1:
            active_range += f" → {active['end_date']}"
    values = [
        ("Date range", active_range, preview.date_range_label),
        (
            "Experiment days",
            active.get("num_days") if active else None,
            preview.num_days,
        ),
        (
            "Daily time points",
            active.get("daily_time_points") if active else None,
            preview.daily_time_points,
        ),
        (
            "Technical replicates",
            active.get("replicates") if active else None,
            preview.replicates,
        ),
        (
            "Replicate spacing",
            f'{active.get("replicate_interval_seconds")} s' if active else None,
            f"{preview.replicate_interval_seconds} s",
        ),
        (
            "Daily captures",
            active.get("daily_captures") if active else None,
            preview.daily_captures,
        ),
        (
            "Total captures",
            active.get("total_captures") if active else None,
            preview.total_captures,
        ),
    ]
    rows = [
        {"label": label, "active": old, "draft": new, "changed": old != new}
        for label, old, new in values
    ]
    return ScheduleComparison(
        rows=rows,
        has_active_schedule=active is not None,
        changed=any(row["changed"] for row in rows),
    )


def _schedule_hash(schedule: dict[str, Any]) -> str:
    return hashlib.sha256(schedule_json(schedule).encode()).hexdigest()


def build_schedule_preview(
    *,
    mode: str,
    start_date: str,
    num_days: int,
    replicates: int,
    replicate_interval_seconds: int,
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
    _validate_start_date(start_date)
    times = _build_times(
        mode=mode,
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

    validate_schedule_size(
        num_days=num_days,
        daily_time_points=len(times),
        replicates=replicates,
        replicate_interval_seconds=replicate_interval_seconds,
    )
    try:
        date.fromisoformat(start_date) + timedelta(days=num_days - 1)
    except OverflowError as exc:
        raise ValueError(
            "The experiment date range exceeds the supported calendar."
        ) from exc

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
    )


def _build_times(
    *,
    mode: str,
    every_start: str | None,
    every_end: str | None,
    every_step_minutes: int | None,
    duration_start: str | None,
    duration_minutes: int | None,
    duration_step_minutes: int | None,
    centered_center: str | None,
    centered_before_minutes: int | None,
    centered_after_minutes: int | None,
    centered_step_minutes: int | None,
) -> list[str]:
    if mode == "every":
        if every_start is None or every_end is None or every_step_minutes is None:
            raise ValueError("Every mode requires start, end, and step minutes.")

        return every_n_minutes(every_start, every_end, every_step_minutes)

    if mode == "duration":
        if duration_start is None or duration_minutes is None or duration_step_minutes is None:
            raise ValueError("Duration mode requires start, duration, and step minutes.")

        return every_n_minutes_for_duration(
            duration_start,
            duration_minutes,
            duration_step_minutes,
        )

    if mode == "centered":
        if (
            centered_center is None
            or centered_before_minutes is None
            or centered_after_minutes is None
            or centered_step_minutes is None
        ):
            raise ValueError("Centered mode requires center, before, after, and step minutes.")

        return centered_time_range(
            centered_center,
            centered_before_minutes,
            centered_after_minutes,
            centered_step_minutes,
        )

    raise ValueError(f"Unknown schedule mode: {mode!r}.")


def _validate_start_date(start_date: str) -> None:
    try:
        parsed = date.fromisoformat(start_date)
    except ValueError as exc:
        raise ValueError("Start date must use YYYY-MM-DD format.") from exc
    if parsed < date.today():
        raise PastStartDateError("Start date cannot be in the past.")


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour) * 60 + int(minute)
