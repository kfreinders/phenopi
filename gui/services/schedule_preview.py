from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from gui.config import DEFAULT_SCHEDULE_PATH, PROJECT_ROOT
from scripts.scheduling.make_schedule import (
    centered_time_range,
    every_n_minutes,
    every_n_minutes_for_duration,
    validate_unique_expanded_times,
    write_schedule,
)


class ScheduleFormData(BaseModel):
    """Typed representation of the schedule builder's submitted fields."""

    mode: str
    start_date: str
    num_days: int
    replicates: int
    replicate_interval_seconds: int
    output: str
    overwrite: bool = False
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
        return self.model_dump()


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

    @property
    def json_text(self) -> str:
        return json.dumps(self.as_schedule_dict(), indent=2)

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
        "start_date": date.today().isoformat(),
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


def resolve_output_path(output: str) -> Path:
    path = Path(output).expanduser()

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def save_schedule_preview(preview: SchedulePreview) -> Path:
    """Persist a validated preview and return its resolved output path."""
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
    return output_path


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
    _validate_start_date(start_date)
    _validate_positive_int(num_days, "Number of days")
    _validate_positive_int(replicates, "Replicates")

    if replicate_interval_seconds < 0:
        raise ValueError("Replicate interval must be 0 or greater.")

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
        date.fromisoformat(start_date)
    except ValueError as exc:
        raise ValueError("Start date must use YYYY-MM-DD format.") from exc


def _validate_positive_int(value: int, label: str) -> None:
    if value <= 0:
        raise ValueError(f"{label} must be greater than 0.")


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour) * 60 + int(minute)
