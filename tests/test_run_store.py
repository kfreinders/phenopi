import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from scripts.scheduling.run_store import RunArchive, run_directory_name


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


def schedule(run_id=None, **overrides):
    value = {
        "start_date": "2026-07-22",
        "num_days": 1,
        "times": ["11:00", "13:00"],
        "replicates": 1,
        "replicate_interval_seconds": 0,
        "run": {
            "id": run_id or str(uuid4()),
            "name": "Drought response / tray A",
            "researcher": "Researcher One",
            "notes": None,
            "created_at": NOW.isoformat(),
        },
    }
    value.update(overrides)
    return value


def test_run_archive_creates_portable_manifest_and_safe_directory(tmp_path):
    configured = schedule()
    archive = RunArchive(tmp_path, configured, "a" * 64, [NOW])

    manifest = json.loads(archive.manifest_path.read_text())
    assert archive.directory.name == run_directory_name(
        configured["start_date"], configured["run"]
    )
    assert "/" not in archive.directory.name
    assert manifest["run"] == configured["run"]
    assert manifest["schedule_hash"] == "a" * 64
    assert manifest["state"] == "active"


def test_capture_ledger_reconstructs_latest_results_and_summary(tmp_path):
    past = NOW - timedelta(hours=1)
    future = NOW + timedelta(hours=1)
    archive = RunArchive(tmp_path, schedule(), "a" * 64, [past, future])
    archive.record(
        scheduled_at=past,
        status="failed",
        message="camera unavailable",
    )
    archive.record(
        scheduled_at=past,
        status="succeeded",
        message="capture job succeeded on retry",
    )

    payload = archive.status_payload(NOW)

    assert payload["summary"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 0,
        "missed": 0,
        "remaining": 1,
        "elapsed_unreported": 0,
    }
    assert payload["last"]["status"] == "succeeded"


def test_run_archive_records_unreported_past_captures_as_missed(tmp_path):
    past = NOW - timedelta(hours=1)
    future = NOW + timedelta(hours=1)
    archive = RunArchive(tmp_path, schedule(), "a" * 64, [past, future])

    archive.record_unreported_past(NOW)

    assert archive.status_payload(NOW)["summary"]["missed"] == 1


def test_capture_ledger_ignores_only_an_interrupted_final_line(tmp_path):
    archive = RunArchive(tmp_path, schedule(), "a" * 64, [NOW])
    archive.record(scheduled_at=NOW, status="succeeded", message="ok")
    with archive.events_path.open("a") as output:
        output.write('{"version":')

    assert len(archive.events()) == 1

    archive.events_path.write_text('{"bad":true}\n{"version":')
    with pytest.raises(ValueError, match="invalid event"):
        archive.events()


def test_run_id_cannot_be_reused_for_another_schedule(tmp_path):
    configured = schedule()
    RunArchive(tmp_path, configured, "a" * 64, [NOW])

    with pytest.raises(ValueError, match="another schedule"):
        RunArchive(tmp_path, configured, "b" * 64, [NOW])


def test_run_can_be_marked_superseded(tmp_path):
    archive = RunArchive(tmp_path, schedule(), "a" * 64, [NOW])

    archive.mark_ended("superseded", superseded_by=str(uuid4()))

    manifest = json.loads(archive.manifest_path.read_text())
    assert manifest["state"] == "superseded"
    assert manifest["ended_at"] is not None
    assert manifest["superseded_by"] is not None
