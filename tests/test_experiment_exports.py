from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import pytest

from gui.services.experiment_exports import (
    ExperimentExportError,
    delete_experiment_data,
    download_path,
    export_details,
    validate_finished_experiment,
)
from scripts.scheduling.run_store import RunArchive


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


def finished_schedule(run_id: UUID) -> dict:
    return {
        "lifecycle": "finished",
        "hash": "a" * 64,
        "start_date": "2026-07-22",
        "end_date": "2026-07-22",
        "run": {
            "id": str(run_id),
            "name": "Finished plants",
            "researcher": "Researcher One",
            "notes": None,
            "created_at": NOW.isoformat(),
        },
    }


def configured_schedule(schedule: dict) -> dict:
    return {
        "start_date": schedule["start_date"],
        "num_days": 1,
        "times": ["12:00"],
        "replicates": 1,
        "replicate_interval_seconds": 0,
        "run": schedule["run"],
    }


def completed_dataset(tmp_path):
    run_id = uuid4()
    schedule = finished_schedule(run_id)
    run = RunArchive(
        tmp_path,
        configured_schedule(schedule),
        schedule["hash"],
        [NOW],
    )
    run.mark_ended("completed")
    run._archive_thread.join(timeout=5)
    return run_id, schedule, run


def test_only_current_finished_experiment_can_be_exported():
    run_id = uuid4()
    schedule = finished_schedule(run_id)

    assert validate_finished_experiment(
        {"schedule": schedule}, run_id
    ) == schedule
    schedule["lifecycle"] = "active"
    with pytest.raises(ExperimentExportError, match="no longer available"):
        validate_finished_experiment({"schedule": schedule}, run_id)


def test_export_details_and_download_require_matching_completed_manifest(tmp_path):
    _, schedule, run = completed_dataset(tmp_path)

    details = export_details(tmp_path, schedule)

    assert details["archive_ready"] is True
    assert details["data_present"] is True
    assert details["archive_size_bytes"] > 0
    assert download_path(tmp_path, schedule) == run.archive_path

    manifest = json.loads(run.manifest_path.read_text())
    manifest["schedule_hash"] = "b" * 64
    run.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ExperimentExportError, match="does not match"):
        download_path(tmp_path, schedule)


def test_deletion_removes_only_the_matching_dataset_and_zip(tmp_path):
    _, schedule, run = completed_dataset(tmp_path)
    unrelated = tmp_path / "keep-me"
    unrelated.mkdir()

    delete_experiment_data(tmp_path, schedule)

    assert not run.directory.exists()
    assert not run.archive_path.exists()
    assert unrelated.exists()
