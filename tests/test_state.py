import json

import pytest

from scripts.scheduling.schedule_builder import (
    load_config,
    load_completed_jobs,
    save_completed_jobs,
)


@pytest.mark.parametrize(
    "filename, file_contents, expected",
    [
        (
            "schedule.json",
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": ["09:00"],
            },
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": ["09:00"],
            },
        ),
    ],
)
def test_load_config_valid(tmp_path, filename, file_contents, expected):
    config_path = tmp_path / filename
    config_path.write_text(json.dumps(file_contents))

    result = load_config(config_path)

    assert result == expected


@pytest.mark.parametrize(
    "filename, file_contents",
    [
        ("missing.json", None),
        ("schedule.json", "{invalid json"),
    ],
    ids=[
        "missing-file",
        "invalid-json",
    ],
)
def test_load_config_errors(tmp_path, filename, file_contents):
    config_path = tmp_path / filename

    if file_contents is not None:
        config_path.write_text(file_contents)

    with pytest.raises(RuntimeError):
        load_config(config_path)


def test_load_config_extra_keys_preserved(tmp_path):
    config_path = tmp_path / "schedule.json"
    config_path.write_text(json.dumps({
        "start_date": "2026-04-21",
        "num_days": 1,
        "times": ["09:00"],
        "experiment_name": "salt_stress_run_01",
    }))

    result = load_config(config_path)

    assert result["experiment_name"] == "salt_stress_run_01"


def test_load_config_missing_keys_still_loads(tmp_path):
    config_path = tmp_path / "schedule.json"
    config_path.write_text(json.dumps({
        "start_date": "2026-04-21",
    }))

    result = load_config(config_path)

    assert result == {"start_date": "2026-04-21"}


@pytest.mark.parametrize(
    "file_contents, expected",
    [
        (
            None,
            set(),
        ),
        (
            [
                "2026-04-21T09:00:00+02:00",
                "2026-04-21T15:00:00+02:00",
            ],
            {
                "2026-04-21T09:00:00+02:00",
                "2026-04-21T15:00:00+02:00",
            },
        ),
        (
            {"a": 1},
            set(),
        ),
        (
            "{invalid json",
            set(),
        ),
    ],
    ids=[
        "missing-file",
        "valid-list",
        "non-list-json",
        "invalid-json",
    ],
)
def test_load_completed_jobs_cases(tmp_path, file_contents, expected):
    state_path = tmp_path / "completed_jobs.json"

    if file_contents is None:
        pass
    elif isinstance(file_contents, str):
        state_path.write_text(file_contents)
    else:
        state_path.write_text(json.dumps(file_contents))

    result = load_completed_jobs(state_path)

    assert result == expected


@pytest.mark.parametrize(
    "completed",
    [
        {
            "2026-04-21T15:00:00+02:00",
            "2026-04-21T09:00:00+02:00",
        },
        set(),
        {
            "2026-04-21T09:00:00+02:00",
        },
    ],
    ids=[
        "multiple-items",
        "empty-set",
        "single-item",
    ],
)
def test_save_completed_jobs_roundtrip(tmp_path, completed):
    state_path = tmp_path / "completed_jobs.json"

    save_completed_jobs(state_path, completed)

    loaded = load_completed_jobs(state_path)
    assert loaded == completed


def test_load_completed_jobs_duplicates_removed(tmp_path):
    state_path = tmp_path / "completed_jobs.json"
    state_path.write_text(json.dumps([
        "2026-04-21T09:00:00+02:00",
        "2026-04-21T09:00:00+02:00",
    ]))

    result = load_completed_jobs(state_path)

    assert result == {"2026-04-21T09:00:00+02:00"}


def test_save_completed_jobs_writes_sorted(tmp_path):
    state_path = tmp_path / "completed_jobs.json"

    completed = {
        "2026-04-21T15:00:00+02:00",
        "2026-04-21T09:00:00+02:00",
    }

    save_completed_jobs(state_path, completed)

    raw = json.loads(state_path.read_text())

    assert raw == sorted(completed)


def test_save_completed_jobs_no_tmp_file_left(tmp_path):
    state_path = tmp_path / "completed_jobs.json"

    completed = {"a", "b"}

    save_completed_jobs(state_path, completed)

    tmp_path_file = state_path.with_suffix(".tmp")

    assert not tmp_path_file.exists()
    assert state_path.exists()
