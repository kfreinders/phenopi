from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


HEARTBEAT_FILENAME = "scheduler-heartbeat.json"
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_STATES = {
    "running",
    "waiting_for_schedule",
    "invalid_schedule",
}


class SchedulerHeartbeat:
    """Write the scheduler's current state to an atomic JSON heartbeat."""

    def __init__(self, runtime_dir: Path) -> None:
        self.path = runtime_dir / HEARTBEAT_FILENAME
        self._state = "waiting_for_schedule"
        self._message = "The scheduler is waiting for a schedule file."
        self._lock = Lock()

    def set_state(self, state: str, message: str) -> bool:
        """Set the current state and immediately publish a heartbeat."""
        if state not in HEARTBEAT_STATES:
            raise ValueError(f"Unsupported scheduler heartbeat state: {state}")

        with self._lock:
            self._state = state
            self._message = message
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
        }

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
