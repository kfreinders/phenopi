from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import subprocess
import time
from pathlib import Path
from typing import Any

from scripts.analysis.queue import AnalysisQueue
from scripts.scheduling.config import SchedulerConfig
from scripts.scheduling.run_store import RunArchive


ANALYSIS_POLL_SECONDS = 15
DEFAULT_ANALYSIS_SECONDS = 5 * 60
CAPTURE_SAFETY_SECONDS = 60
MAX_ANALYSIS_SECONDS = 60 * 60


@dataclass(frozen=True)
class AnalysisWindow:
    available: bool
    reason: str
    timeout_seconds: float | None = None
    next_safe_at: datetime | None = None


def find_analysis_window(
    now: datetime,
    run_times: list[datetime],
    capture_events: list[dict[str, Any]],
    *,
    required_seconds: float = DEFAULT_ANALYSIS_SECONDS,
    safety_seconds: float = CAPTURE_SAFETY_SECONDS,
) -> AnalysisWindow:
    """Return whether analysis can finish before the next protected capture."""
    latest_results = {
        event["capture_id"]: event
        for event in capture_events
        if event.get("capture_id")
    }
    unresolved = [
        run_time
        for run_time in run_times
        if run_time <= now and run_time.isoformat() not in latest_results
    ]
    if unresolved:
        return AnalysisWindow(False, "waiting_for_capture")

    previous = max((value for value in run_times if value <= now), default=None)
    if previous is not None:
        safe_after = previous + timedelta(seconds=safety_seconds)
        if now < safe_after:
            return AnalysisWindow(
                False,
                "capture_guard",
                next_safe_at=safe_after,
            )

    upcoming = min((value for value in run_times if value > now), default=None)
    if upcoming is None:
        return AnalysisWindow(
            True,
            "after_final_capture",
            timeout_seconds=MAX_ANALYSIS_SECONDS,
        )

    stop_before = upcoming - timedelta(seconds=safety_seconds)
    available_seconds = (stop_before - now).total_seconds()
    if available_seconds < required_seconds:
        return AnalysisWindow(False, "insufficient_time")
    return AnalysisWindow(
        True,
        "safe_gap",
        timeout_seconds=min(available_seconds, MAX_ANALYSIS_SECONDS),
    )


def poll_analysis_queue(
    config: SchedulerConfig,
    run_archive: RunArchive,
    run_times: list[datetime],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Analyze at most one pending capture when the schedule leaves a safe gap."""
    capture_events = run_archive.events()
    queue = AnalysisQueue(run_archive.analysis_dir)
    pending = queue.pending(capture_events)
    summary: dict[str, Any] = queue.summary(capture_events)
    if not pending:
        state.update(summary, state="complete", next_safe_at=None)
        return state

    now = datetime.now(config.tz)
    window = find_analysis_window(now, run_times, capture_events)
    if not window.available:
        state.update(
            summary,
            state="waiting",
            reason=window.reason,
            next_safe_at=(
                window.next_safe_at.isoformat()
                if window.next_safe_at is not None
                else None
            ),
        )
        return state

    capture = pending[0]
    capture_id = capture["capture_id"]
    state.update(
        summary,
        state="running",
        capture_id=capture_id,
        next_safe_at=None,
    )
    queue.record(
        capture_id=capture_id,
        image_path=capture["image_path"],
        status="running",
        message="Analysis started.",
    )
    started = time.monotonic()
    try:
        image_path = _resolve_capture_path(run_archive, capture["image_path"])
        if not image_path.is_file():
            raise FileNotFoundError("The captured image is no longer available.")
        subprocess.run(
            [
                str(config.python_bin),
                "-m",
                "scripts.analysis.analyze_one",
                "--image",
                str(image_path),
                "--analysis-dir",
                str(run_archive.analysis_dir),
            ],
            check=True,
            cwd=config.capture_script.parents[2],
            timeout=window.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        message = "Analysis was paused to protect the next capture."
        status = "failed"
    except subprocess.CalledProcessError as exc:
        message = f"Analysis exited with status {exc.returncode}."
        status = "failed"
    except (FileNotFoundError, ValueError) as exc:
        message = str(exc)
        status = "failed"
    except OSError as exc:
        message = f"Analysis could not be started: {exc}"
        status = "failed"
    else:
        message = "Analysis completed successfully."
        status = "succeeded"

    queue.record(
        capture_id=capture_id,
        image_path=capture["image_path"],
        status=status,
        message=message,
        duration_seconds=time.monotonic() - started,
    )
    state.update(
        queue.summary(capture_events),
        state="idle" if status == "succeeded" else "waiting",
        reason=None if status == "succeeded" else "analysis_failed",
        capture_id=None,
    )
    return state


def _resolve_capture_path(run_archive: RunArchive, relative_path: str) -> Path:
    candidate = (run_archive.directory / relative_path).resolve()
    try:
        candidate.relative_to(run_archive.directory.resolve())
    except ValueError as exc:
        raise ValueError("Analysis image path escapes the run directory.") from exc
    return candidate
