from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from collections.abc import Callable


HEARTBEAT_FILENAME = "scheduler-heartbeat.json"
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_STATES = {
    "running",
    "waiting_for_schedule",
    "invalid_schedule",
}
_KEEP_SCHEDULE = object()


class SchedulerHeartbeat:
    """Write the scheduler's current state to an atomic JSON heartbeat."""

    def __init__(
        self,
        runtime_dir: Path,
        storage_path: Path | None = None,
    ) -> None:
        self.path = runtime_dir / HEARTBEAT_FILENAME
        self.storage_path = storage_path
        self._state = "waiting_for_schedule"
        self._message = "The scheduler is waiting for a schedule file."
        self._schedule: dict | None = None
        self._last_capture = self._load_previous_capture()
        self._capture_status_provider: Callable[[], dict] | None = None
        self._lock = Lock()

    def set_capture_status_provider(
        self,
        provider: Callable[[], dict] | None,
    ) -> None:
        with self._lock:
            self._capture_status_provider = provider

    def set_state(
        self,
        state: str,
        message: str,
        *,
        schedule: dict | None | object = _KEEP_SCHEDULE,
    ) -> bool:
        """Set the current state and immediately publish a heartbeat."""
        if state not in HEARTBEAT_STATES:
            raise ValueError(f"Unsupported scheduler heartbeat state: {state}")

        with self._lock:
            self._state = state
            self._message = message
            if schedule is not _KEEP_SCHEDULE:
                self._schedule = schedule
                if schedule is None:
                    self._last_capture = None
                elif (
                    self._last_capture is not None
                    and self._last_capture.get("schedule_hash")
                    != schedule.get("hash")
                ):
                    self._last_capture = None
            return self._write_locked()

    def record_capture(self, result: dict) -> bool:
        """Publish the latest actual capture-job outcome."""
        with self._lock:
            self._last_capture = result
            return self._write_locked()

    def write(self) -> bool:
        """Refresh the heartbeat timestamp without changing its state."""
        with self._lock:
            return self._write_locked()

    def _write_locked(self) -> bool:
        temporary_path = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.tmp"
        )
        payload = {
            "version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": self._state,
            "message": self._message,
            "schedule": self._schedule,
            "last_capture": self._last_capture,
            "storage": self._storage_payload(),
        }
        if self._capture_status_provider is not None:
            capture_status = self._capture_status_provider()
            payload["capture_summary"] = capture_status.get("summary")
            payload["recent_captures"] = capture_status.get("recent", [])
            payload["last_capture"] = capture_status.get("last")
            payload["daily_capture_progress"] = capture_status.get("daily_progress")
        else:
            payload["capture_summary"] = None
            payload["recent_captures"] = []
            payload["daily_capture_progress"] = None

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(json.dumps(payload) + "\n")
            temporary_path.replace(self.path)
        except OSError as exc:
            print(
                f"[scheduler] Could not write heartbeat: {exc}",
                file=sys.stderr,
            )
            return False

        return True

    def _load_previous_capture(self) -> dict | None:
        try:
            payload = json.loads(self.path.read_text())
            result = payload.get("last_capture")
            return result if isinstance(result, dict) else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _storage_payload(self) -> dict | None:
        if self.storage_path is None:
            return None
        path = self.storage_path
        while not path.exists() and path != path.parent:
            path = path.parent
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return None
        used = usage.total - usage.free
        return {
            "total_bytes": usage.total,
            "used_bytes": used,
            "free_bytes": usage.free,
            "used_percent": round(used / usage.total * 100, 1),
        }
