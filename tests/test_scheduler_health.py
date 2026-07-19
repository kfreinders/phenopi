import json
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from gui.app import app
from gui.config import APP_DIR, static_version, templates
from gui.services.scheduler_status import (
    build_daily_activity,
    build_schedule_overview,
    read_scheduler_health,
    read_scheduler_status,
)
from scripts.scheduling.heartbeat import SchedulerHeartbeat


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def write_heartbeat(
    path,
    *,
    state,
    age_seconds=0,
    message="state message",
    schedule=None,
    last_capture=None,
    storage=None,
):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "timestamp": (NOW - timedelta(seconds=age_seconds)).isoformat(),
                "state": state,
                "message": message,
                "schedule": schedule,
                "last_capture": last_capture,
                "storage": storage,
            }
        )
    )


def test_heartbeat_atomically_writes_current_state(tmp_path):
    heartbeat = SchedulerHeartbeat(tmp_path)

    assert heartbeat.set_state("running", "Scheduler is running.") is True

    payload = json.loads(heartbeat.path.read_text())
    assert payload["version"] == 1
    assert payload["state"] == "running"
    assert payload["message"] == "Scheduler is running."
    assert payload["schedule"] is None
    assert payload["timestamp"].endswith("+00:00")
    assert list(tmp_path.iterdir()) == [heartbeat.path]


def test_heartbeat_rejects_unknown_state(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        SchedulerHeartbeat(tmp_path).set_state("unknown", "message")


def test_heartbeat_retains_or_clears_loaded_schedule(tmp_path):
    heartbeat = SchedulerHeartbeat(tmp_path)
    snapshot = schedule_snapshot()
    heartbeat.set_state("running", "running", schedule=snapshot)

    heartbeat.set_state("invalid_schedule", "rejected edit")
    assert json.loads(heartbeat.path.read_text())["schedule"] == snapshot

    heartbeat.set_state(
        "waiting_for_schedule",
        "waiting",
        schedule=None,
    )
    assert json.loads(heartbeat.path.read_text())["schedule"] is None


def test_heartbeat_write_failure_is_non_fatal(tmp_path):
    runtime_path = tmp_path / "runtime-file"
    runtime_path.write_text("not a directory")

    assert SchedulerHeartbeat(runtime_path).write() is False


def test_heartbeat_reports_capture_storage(tmp_path, monkeypatch):
    usage = shutil._ntuple_diskusage(1000, 600, 400)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage)
    heartbeat = SchedulerHeartbeat(tmp_path, storage_path=tmp_path / "captures")

    heartbeat.write()

    storage = json.loads(heartbeat.path.read_text())["storage"]
    assert storage == {
        "total_bytes": 1000,
        "used_bytes": 600,
        "free_bytes": 400,
        "used_percent": 60.0,
    }


def test_heartbeat_restores_capture_for_same_schedule(tmp_path):
    previous = {
        "schedule_hash": "abcdef1234567890",
        "status": "succeeded",
    }
    (tmp_path / "scheduler-heartbeat.json").write_text(
        json.dumps({"last_capture": previous})
    )
    heartbeat = SchedulerHeartbeat(tmp_path)

    heartbeat.set_state("running", "running", schedule=schedule_snapshot())

    assert json.loads(heartbeat.path.read_text())["last_capture"] == previous


def test_heartbeat_clears_capture_for_replacement_schedule(tmp_path):
    heartbeat = SchedulerHeartbeat(tmp_path)
    heartbeat.record_capture({"schedule_hash": "old", "status": "succeeded"})

    heartbeat.set_state("running", "running", schedule=schedule_snapshot())

    assert json.loads(heartbeat.path.read_text())["last_capture"] is None


@pytest.mark.parametrize(
    ("state", "expected_status"),
    [
        ("running", "healthy"),
        ("waiting_for_schedule", "waiting_for_schedule"),
        ("invalid_schedule", "invalid_schedule"),
    ],
)
def test_status_maps_fresh_scheduler_states(
    tmp_path, state, expected_status
):
    heartbeat_path = tmp_path / "heartbeat.json"
    write_heartbeat(heartbeat_path, state=state, age_seconds=5)

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["status"] == expected_status
    assert result["age_seconds"] == 5.0
    assert result["message"] == "state message"

    health = read_scheduler_health(heartbeat_path, now=NOW)
    assert health == {
        key: result[key]
        for key in ("status", "last_heartbeat_at", "age_seconds", "message")
    }


def test_status_marks_old_heartbeat_stale(tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    write_heartbeat(heartbeat_path, state="running", age_seconds=31)

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["status"] == "stale"
    assert result["age_seconds"] == 31.0


def test_status_exposes_optional_capture_and_storage(tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    capture = {"status": "failed", "message": "camera error"}
    storage = {"free_bytes": 100, "used_percent": 90.0}
    write_heartbeat(
        heartbeat_path,
        state="running",
        last_capture=capture,
        storage=storage,
    )

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["last_capture"] == capture
    assert result["storage"] == storage


def schedule_snapshot():
    return {
        "hash": "abcdef1234567890",
        "timezone": "Europe/Amsterdam",
        "start_date": "2026-07-18",
        "num_days": 2,
        "times": ["09:00", "15:00"],
        "replicates": 2,
        "replicate_interval_seconds": 10,
    }


@pytest.mark.parametrize(
    ("now", "lifecycle", "elapsed", "remaining"),
    [
        (datetime(2026, 7, 18, 6, tzinfo=timezone.utc), "upcoming", 0, 8),
        (datetime(2026, 7, 18, 10, tzinfo=timezone.utc), "active", 2, 6),
        (datetime(2026, 7, 20, 10, tzinfo=timezone.utc), "finished", 8, 0),
    ],
)
def test_schedule_overview_lifecycle(now, lifecycle, elapsed, remaining):
    overview = build_schedule_overview(schedule_snapshot(), now=now)

    assert overview["lifecycle"] == lifecycle
    assert overview["elapsed_captures"] == elapsed
    assert overview["remaining_captures"] == remaining
    assert overview["total_captures"] == 8


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 7, 18, 6, tzinfo=timezone.utc),
        datetime(2026, 7, 18, 16, tzinfo=timezone.utc),
    ],
)
def test_current_calendar_day_is_highlighted_outside_capture_window(now):
    overview = build_schedule_overview(schedule_snapshot(), now=now)

    assert overview["days"][0]["status"] == "current"
    assert overview["days"][1]["status"] == "upcoming"


def test_daily_activity_aggregates_hours_and_window():
    activity = build_daily_activity(
        ["08:00", "08:30", "09:00", "09:30"],
        replicates=3,
    )

    assert len(activity["hours"]) == 24
    assert activity["hours"][8]["time_point_count"] == 2
    assert activity["hours"][8]["capture_count"] == 6
    assert activity["hours"][9]["capture_count"] == 6
    assert activity["hours"][8]["intensity_percent"] == 100.0
    assert activity["window_label"] == "08:00–09:30"
    assert activity["window_minutes"] == 90
    assert activity["window_duration_label"] == "1 hr 30 min"
    assert activity["peak_time_points_per_hour"] == 2
    assert activity["peak_captures_per_hour"] == 6


@pytest.mark.parametrize(
    ("times", "kind", "label"),
    [
        ([], "empty", "No time points"),
        (["08:00"], "single", "Single time point"),
        (["08:00", "08:30", "09:00"], "regular", "Every 30 min"),
        (
            ["08:00", "08:30", "09:00", "09:30", "10:15"],
            "typical",
            "Typically every 30 min",
        ),
        (["08:00", "08:15", "09:00", "10:30"], "variable", "Variable intervals"),
    ],
)
def test_daily_activity_summarizes_cadence(times, kind, label):
    activity = build_daily_activity(times)

    assert activity["cadence_kind"] == kind
    assert activity["cadence_label"] == label


def test_stale_status_retains_last_reported_schedule(tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    write_heartbeat(
        heartbeat_path,
        state="running",
        age_seconds=31,
        schedule=schedule_snapshot(),
    )

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["status"] == "stale"
    assert result["schedule"]["lifecycle"] == "active"
    assert result["schedule_is_last_reported"] is True


def test_invalid_schedule_snapshot_does_not_hide_health(tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    write_heartbeat(
        heartbeat_path,
        state="running",
        schedule={"invalid": "snapshot"},
    )

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["status"] == "healthy"
    assert result["schedule"] is None
    assert result["schedule_error"] is not None


@pytest.mark.parametrize("contents", [None, "not json", "{}"])
def test_status_marks_missing_or_invalid_heartbeat_unavailable(
    tmp_path, contents
):
    heartbeat_path = tmp_path / "heartbeat.json"
    if contents is not None:
        heartbeat_path.write_text(contents)

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["status"] == "unavailable"
    assert result["last_heartbeat_at"] is None
    assert result["age_seconds"] is None

    health = read_scheduler_health(heartbeat_path, now=NOW)
    assert set(health) == {
        "status",
        "last_heartbeat_at",
        "age_seconds",
        "message",
    }
    assert health["status"] == "unavailable"


def test_scheduler_status_routes_are_registered():
    assert str(app.url_path_for("scheduler_status_page")) == "/scheduler"
    assert str(app.url_path_for("scheduler_status_api")) == (
        "/api/scheduler/status"
    )
    assert str(app.url_path_for("scheduler_health_api")) == (
        "/api/scheduler/health"
    )


def test_scheduler_dashboard_assets_are_cache_busted():
    scheduler_source, _, _ = templates.env.loader.get_source(
        templates.env, "scheduler.html"
    )
    base_source, _, _ = templates.env.loader.get_source(
        templates.env, "base.html"
    )

    assert scheduler_source.count("?v={{ static_version(") == 2
    assert base_source.count("?v={{ static_version(") == 2
    assert static_version("scheduler_health.js") > 0


def test_page_assets_are_isolated_and_cache_busted():
    base_source, _, _ = templates.env.loader.get_source(
        templates.env, "base.html"
    )
    schedule_source, _, _ = templates.env.loader.get_source(
        templates.env, "schedule.html"
    )
    camera_source, _, _ = templates.env.loader.get_source(
        templates.env, "camera.html"
    )

    assert "visual_preview.css" not in base_source
    assert "updateModeSections" not in base_source
    assert "visual_preview.css" in schedule_source
    assert "schedule.js" in schedule_source
    assert "camera_preview.css" in camera_source
    assert "camera_preview.js" in camera_source
    assert schedule_source.count("?v={{ static_version(") == 2
    assert camera_source.count("?v={{ static_version(") == 2


def test_global_health_poll_uses_lightweight_endpoint():
    health_script = (APP_DIR / "static" / "scheduler_health.js").read_text()
    dashboard_script = (APP_DIR / "static" / "scheduler_status.js").read_text()

    assert 'fetch("/api/scheduler/health"' in health_script
    assert 'fetch("/api/scheduler/status"' not in health_script
    assert 'fetch("/api/scheduler/status"' in dashboard_script
    assert "scheduler-status-updated" in health_script
    assert "scheduler-status-updated" in dashboard_script
