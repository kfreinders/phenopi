from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from .schedule_validation import (
    validate_replicate_windows,
    validate_schedule_size,
    validate_unique_values,
)


@dataclass(frozen=True)
class RunMetadata:
    id: str
    name: str
    created_at: datetime
    researcher: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunMetadata":
        try:
            run_id = str(UUID(str(value["id"])))
            name = str(value["name"]).strip()
            created_at = datetime.fromisoformat(str(value["created_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("run metadata is invalid") from exc
        if not name or len(name) > 80:
            raise ValueError("run name must contain 1 to 80 characters")
        if created_at.tzinfo is None:
            raise ValueError("run created_at must include a timezone")
        return cls(
            id=run_id,
            name=name,
            created_at=created_at,
            researcher=_optional_text(value.get("researcher"), 80, "researcher"),
            notes=_optional_text(value.get("notes"), 1000, "notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "researcher": self.researcher,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class Schedule:
    start_date: date
    num_days: int
    times: tuple[time, ...]
    replicates: int = 1
    replicate_interval_seconds: int = 0
    run: RunMetadata | None = None

    def __post_init__(self) -> None:
        validate_schedule_size(
            num_days=self.num_days,
            daily_time_points=len(self.times),
            replicates=self.replicates,
            replicate_interval_seconds=self.replicate_interval_seconds,
        )
        validate_replicate_windows(
            [value.hour * 3600 + value.minute * 60 for value in self.times],
            replicates=self.replicates,
            replicate_interval_seconds=self.replicate_interval_seconds,
        )
        try:
            self.start_date + timedelta(days=self.num_days - 1)
        except OverflowError as exc:
            raise ValueError(
                "schedule date range exceeds the supported calendar"
            ) from exc

    @classmethod
    def create(
        cls,
        *,
        start_date: str | date,
        num_days: int,
        times: list[str] | tuple[str, ...],
        replicates: int = 1,
        replicate_interval_seconds: int = 0,
        run: Mapping[str, Any] | RunMetadata | None = None,
        deduplicate_times: bool = False,
    ) -> "Schedule":
        parsed_date = _parse_date(start_date)
        parsed_times = tuple(_parse_time(value) for value in times)
        if deduplicate_times:
            parsed_times = tuple(sorted(set(parsed_times)))
        else:
            validate_unique_values(parsed_times, label="schedule")
            parsed_times = tuple(sorted(parsed_times))
        parsed_run = (
            run
            if isinstance(run, RunMetadata)
            else RunMetadata.from_dict(run) if run is not None else None
        )
        return cls(
            start_date=parsed_date,
            num_days=int(num_days),
            times=parsed_times,
            replicates=int(replicates),
            replicate_interval_seconds=int(replicate_interval_seconds),
            run=parsed_run,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Schedule":
        for field in ("start_date", "num_days", "times"):
            if field not in value:
                raise ValueError(f"schedule is missing required field {field!r}")
        try:
            return cls.create(
                start_date=value["start_date"],
                num_days=value["num_days"],
                times=value["times"],
                replicates=value.get("replicates", 1),
                replicate_interval_seconds=value.get(
                    "replicate_interval_seconds", 0
                ),
                run=value.get("run"),
                deduplicate_times=True,
            )
        except TypeError as exc:
            raise ValueError("schedule data is invalid") from exc

    @classmethod
    def from_json(cls, contents: str) -> "Schedule":
        value = json.loads(contents)
        if not isinstance(value, dict):
            raise ValueError("schedule must be a JSON object")
        return cls.from_dict(value)

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.num_days - 1)

    @property
    def daily_time_points(self) -> int:
        return len(self.times)

    @property
    def daily_captures(self) -> int:
        return self.daily_time_points * self.replicates

    @property
    def total_captures(self) -> int:
        return self.daily_captures * self.num_days

    def expand(self, tz: ZoneInfo) -> list[datetime]:
        jobs = []
        for day_offset in range(self.num_days):
            current_day = self.start_date + timedelta(days=day_offset)
            for capture_time in self.times:
                base = datetime.combine(current_day, capture_time, tzinfo=tz)
                for replicate in range(self.replicates):
                    jobs.append(
                        base
                        + timedelta(
                            seconds=replicate * self.replicate_interval_seconds
                        )
                    )
        validate_unique_values(jobs, label="expanded schedule")
        return sorted(jobs)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "start_date": self.start_date.isoformat(),
            "num_days": self.num_days,
            "replicates": self.replicates,
            "replicate_interval_seconds": self.replicate_interval_seconds,
            "times": [value.strftime("%H:%M") for value in self.times],
        }
        if self.run is not None:
            value["run"] = self.run.to_dict()
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()

def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("start_date must use YYYY-MM-DD format") from exc


def _parse_time(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid time format {value!r}, expected HH:MM") from exc


def _optional_text(value: Any, limit: int, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"run {label} must be text")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > limit:
        raise ValueError(f"run {label} must be {limit} characters or fewer")
    return normalized
