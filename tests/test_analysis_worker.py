from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from types import SimpleNamespace

from scripts.analysis.queue import AnalysisQueue
from scripts.analysis.worker import (
    _analysis_environment_error,
    find_analysis_window,
    poll_analysis_queue,
)
from scripts.scheduling.run_store import RunArchive


NOW = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)


def schedule():
    return {
        "start_date": "2026-07-23",
        "num_days": 1,
        "times": ["11:00"],
        "replicates": 1,
        "replicate_interval_seconds": 0,
        "run": {
            "id": "a88d4586-608d-45a7-a841-d68a7d6aa5e9",
            "name": "Tray A",
            "researcher": "Researcher",
            "notes": None,
            "created_at": NOW.isoformat(),
        },
    }


def result(run_time):
    return {
        "capture_id": run_time.isoformat(),
        "scheduled_at": run_time.isoformat(),
        "status": "succeeded",
        "image_path": "capture.jpg",
    }


def test_analysis_waits_for_an_elapsed_capture_result():
    run_time = NOW - timedelta(minutes=5)

    window = find_analysis_window(NOW, [run_time], [])

    assert window.available is False
    assert window.reason == "waiting_for_capture"


def test_analysis_requires_enough_time_before_the_next_capture():
    previous = NOW - timedelta(minutes=5)
    upcoming = NOW + timedelta(minutes=5)

    window = find_analysis_window(
        NOW,
        [previous, upcoming],
        [result(previous)],
    )

    assert window.available is False
    assert window.reason == "insufficient_time"


def test_analysis_uses_a_long_gap_between_captures():
    previous = NOW - timedelta(minutes=5)
    upcoming = NOW + timedelta(minutes=10)

    window = find_analysis_window(
        NOW,
        [previous, upcoming],
        [result(previous)],
    )

    assert window.available is True
    assert window.reason == "safe_gap"
    assert window.timeout_seconds == 9 * 60


def test_worker_analyzes_one_pending_capture(tmp_path, monkeypatch):
    run_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    archive = RunArchive(
        tmp_path / "captures",
        schedule(),
        "a" * 64,
        [run_time],
    )
    image_path = archive.capture_path(run_time)
    image_path.touch()
    archive.record(
        scheduled_at=run_time,
        status="succeeded",
        message="ok",
        image_path=image_path,
    )
    capture_script = tmp_path / "project" / "scripts" / "capture" / "capture_once.py"
    called = {}

    def run(command, **kwargs):
        called["command"] = command
        called["kwargs"] = kwargs

    monkeypatch.setattr("scripts.analysis.worker.subprocess.run", run)
    config = SimpleNamespace(
        python_bin=Path("/venv/bin/python"),
        capture_script=capture_script,
        tz=timezone.utc,
    )

    state = {}
    poll_analysis_queue(config, archive, [run_time], state)

    assert called["command"][:3] == [
        "/venv/bin/python",
        "-m",
        "scripts.analysis.analyze_one",
    ]
    assert called["kwargs"]["check"] is True
    assert state["succeeded"] == 1
    assert AnalysisQueue(archive.analysis_dir).pending(archive.events()) == []


def test_missing_analysis_dependencies_are_reported_before_an_attempt(
    tmp_path,
    monkeypatch,
):
    config = SimpleNamespace(
        python_bin=Path("/incomplete/bin/python"),
        capture_script=(
            tmp_path / "project" / "scripts" / "capture" / "capture_once.py"
        ),
    )

    def missing(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr("scripts.analysis.worker.subprocess.run", missing)

    error = _analysis_environment_error(config)

    assert "/incomplete/bin/python" in error
