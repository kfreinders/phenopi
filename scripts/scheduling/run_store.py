from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any

from .make_schedule import atomic_write_text
from .schedule import RunMetadata, Schedule


RUN_MANIFEST_VERSION = 1
CAPTURE_EVENT_VERSION = 1
_SAFE_NAME = re.compile(r"[^a-z0-9]+")


def validate_run_metadata(value: Any) -> dict[str, Any] | None:
    """Validate optional run metadata while retaining legacy compatibility."""
    if value is None:
        return None
    if isinstance(value, RunMetadata):
        return value.to_dict()
    if not isinstance(value, dict):
        raise ValueError("run must be an object")
    return RunMetadata.from_dict(value).to_dict()


def run_directory_name(start_date: str, run: dict[str, Any]) -> str:
    slug = _SAFE_NAME.sub("-", run["name"].lower()).strip("-") or "experiment"
    return f"{start_date}_{slug[:48]}_{run['id'].replace('-', '')[:8]}"


class RunArchive:
    """Portable run manifest and append-only capture outcome ledger."""

    def __init__(
        self,
        output_root: Path,
        schedule: dict[str, Any] | Schedule,
        schedule_hash: str,
        expected_times: list[datetime],
    ) -> None:
        schedule_data = schedule.to_dict() if isinstance(schedule, Schedule) else schedule
        run = validate_run_metadata(schedule_data.get("run"))
        if run is None:
            raise ValueError("A run archive requires run metadata.")
        self.run = run
        self.schedule_hash = schedule_hash
        self.expected_times = expected_times
        self.directory = output_root / run_directory_name(schedule_data["start_date"], run)
        self.manifest_path = self.directory / "run.json"
        self.events_path = self.directory / "capture-events.jsonl"
        self._lock = Lock()
        self._initialize(schedule_data)

    def _initialize(self, schedule: dict[str, Any]) -> None:
        existing_path = self._find_existing_manifest(self.directory.parent)
        if existing_path is not None and existing_path != self.manifest_path:
            raise ValueError("This run ID is already used by another dataset directory.")
        if self.manifest_path.exists():
            manifest = self._read_manifest()
            if (manifest.get("run") or {}).get("id") != self.run["id"]:
                raise ValueError("The dataset directory belongs to another run.")
            if manifest.get("schedule_hash") != self.schedule_hash:
                raise ValueError("This run ID is already associated with another schedule.")
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        manifest = {
            "version": RUN_MANIFEST_VERSION,
            "run": self.run,
            "schedule_hash": self.schedule_hash,
            "schedule": schedule,
            "dataset_directory": str(self.directory),
            "loaded_at": datetime.now(timezone.utc).isoformat(),
            "state": "active",
            "ended_at": None,
            "superseded_by": None,
        }
        atomic_write_text(self.manifest_path, json.dumps(manifest, indent=2) + "\n")

    def _find_existing_manifest(self, output_root: Path) -> Path | None:
        for path in output_root.glob("*/run.json") if output_root.exists() else []:
            try:
                manifest = json.loads(path.read_text())
            except (OSError, ValueError, TypeError):
                continue
            if (manifest.get("run") or {}).get("id") == self.run["id"]:
                return path
        return None

    def _read_manifest(self) -> dict[str, Any]:
        try:
            manifest = json.loads(self.manifest_path.read_text())
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("The run manifest could not be read.") from exc
        if manifest.get("version") != RUN_MANIFEST_VERSION:
            raise ValueError("The run manifest version is unsupported.")
        return manifest

    def mark_ended(self, state: str, *, superseded_by: str | None = None) -> None:
        if state not in {"completed", "superseded"}:
            raise ValueError("Unsupported terminal run state.")
        with self._lock:
            manifest = self._read_manifest()
            if manifest.get("state") in {"completed", "superseded"}:
                return
            manifest["state"] = state
            manifest["ended_at"] = datetime.now(timezone.utc).isoformat()
            manifest["superseded_by"] = superseded_by if state == "superseded" else None
            atomic_write_text(
                self.manifest_path,
                json.dumps(manifest, indent=2) + "\n",
            )

    def record(
        self,
        *,
        scheduled_at: datetime,
        status: str,
        message: str,
    ) -> dict[str, Any]:
        if status not in {"succeeded", "failed", "missed"}:
            raise ValueError("Unsupported capture result status.")
        event = {
            "version": CAPTURE_EVENT_VERSION,
            "run_id": self.run["id"],
            "schedule_hash": self.schedule_hash,
            "capture_id": scheduled_at.isoformat(),
            "scheduled_at": scheduled_at.isoformat(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "message": message,
        }
        line = json.dumps(event, separators=(",", ":")) + "\n"
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a") as output:
                output.write(line)
                output.flush()
                os.fsync(output.fileno())
        return event

    def events(self) -> list[dict[str, Any]]:
        try:
            contents = self.events_path.read_text()
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise ValueError("The capture ledger could not be read.") from exc
        events = []
        lines = contents.splitlines(keepends=True)
        for index, line in enumerate(lines):
            try:
                event = json.loads(line)
                if event.get("version") != CAPTURE_EVENT_VERSION:
                    raise ValueError("unsupported event")
            except (ValueError, TypeError):
                if index == len(lines) - 1 and not line.endswith("\n"):
                    break
                raise ValueError("The capture ledger contains an invalid event.")
            events.append(event)
        return events

    def latest_events(self) -> dict[str, dict[str, Any]]:
        return {event["capture_id"]: event for event in self.events()}

    def record_unreported_past(self, now: datetime) -> None:
        recorded = self.latest_events()
        for scheduled_at in self.expected_times:
            capture_id = scheduled_at.isoformat()
            if scheduled_at < now and capture_id not in recorded:
                self.record(
                    scheduled_at=scheduled_at,
                    status="missed",
                    message="The schedule was loaded after this capture time.",
                )

    def status_payload(self, now: datetime) -> dict[str, Any]:
        latest = self.latest_events()
        events = list(latest.values())
        counts = {status: 0 for status in ("succeeded", "failed", "missed")}
        for event in events:
            counts[event["status"]] += 1
        expected_ids = {value.isoformat() for value in self.expected_times}
        remaining = sum(value >= now for value in self.expected_times)
        elapsed_unreported = sum(
            value < now and value.isoformat() not in latest
            for value in self.expected_times
        )
        recent = sorted(
            (event for event in events if event["capture_id"] in expected_ids),
            key=lambda event: event["recorded_at"],
            reverse=True,
        )[:5]
        return {
            "summary": {
                "total": len(self.expected_times),
                **counts,
                "remaining": remaining,
                "elapsed_unreported": elapsed_unreported,
            },
            "recent": recent,
            "last": recent[0] if recent else None,
        }
