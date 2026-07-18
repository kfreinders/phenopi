import json
from datetime import datetime, timedelta, timezone

import pytest

from gui.app import app
from gui.services.scheduler_status import (
    build_daily_chart,
    build_schedule_overview,
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
):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "timestamp": (NOW - timedelta(seconds=age_seconds)).isoformat(),
                "state": state,
                "message": message,
                "schedule": schedule,
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


def test_status_marks_old_heartbeat_stale(tmp_path):
    heartbeat_path = tmp_path / "heartbeat.json"
    write_heartbeat(heartbeat_path, state="running", age_seconds=31)

    result = read_scheduler_status(heartbeat_path, now=NOW)

    assert result["status"] == "stale"
    assert result["age_seconds"] == 31.0


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


def test_sparse_daily_chart_uses_full_day_marker_positions():
    chart = build_daily_chart(["00:00", "06:00", "12:00", "23:59"])

    assert chart["mode"] == "markers"
    assert [point["percent"] for point in chart["points"][:3]] == [
        0.0,
        25.0,
        50.0,
    ]


def test_daily_chart_switches_to_density_after_marker_limit():
    times = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]

    assert build_daily_chart(times)["mode"] == "markers"
    assert build_daily_chart(times + ["00:15"])["mode"] == "density"


def test_density_chart_aggregates_fifteen_minute_bins():
    chart = build_daily_chart(
        ["08:00", "08:01", "08:15"],
        marker_limit=1,
    )

    assert len(chart["bins"]) == 96
    assert chart["bins"][32] == {
        "start": "08:00",
        "end": "08:15",
        "count": 2,
        "height_percent": 100.0,
    }
    assert chart["bins"][33]["count"] == 1
    assert chart["bins"][33]["height_percent"] == 50.0


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


def test_scheduler_status_routes_are_registered():
    assert str(app.url_path_for("scheduler_status_page")) == "/scheduler"
    assert str(app.url_path_for("scheduler_status_api")) == (
        "/api/scheduler/status"
    )
