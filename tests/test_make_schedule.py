import json

import pytest

from scripts.scheduling.make_schedule import (
    centered_time_range,
    every_n_minutes,
    every_n_minutes_for_duration,
    validate_unique_expanded_times,
    write_schedule,
)
from scripts.scheduling.schedule_validation import ScheduleValidationError


@pytest.mark.parametrize(
    ("start", "end", "step", "expected"),
    [
        ("09:00", "10:00", 30, ["09:00", "09:30", "10:00"]),
        ("09:00", "09:45", 30, ["09:00", "09:30"]),
        ("10:00", "09:00", 30, []),
    ],
)
def test_every_n_minutes(start, end, step, expected):
    assert every_n_minutes(start, end, step) == expected


@pytest.mark.parametrize("step", [0, -1])
def test_every_n_minutes_requires_positive_step(step):
    with pytest.raises(ValueError, match="step_minutes"):
        every_n_minutes("09:00", "10:00", step)


def test_every_n_minutes_rejects_invalid_time():
    with pytest.raises(ValueError):
        every_n_minutes("24:00", "10:00", 30)


@pytest.mark.parametrize(
    ("duration", "step", "expected"),
    [
        (60, 20, ["12:00", "12:20", "12:40", "13:00"]),
        (45, 20, ["12:00", "12:20", "12:40"]),
        (0, 10, ["12:00"]),
    ],
)
def test_every_n_minutes_for_duration(duration, step, expected):
    assert every_n_minutes_for_duration("12:00", duration, step) == expected


@pytest.mark.parametrize(("duration", "step"), [(-1, 10), (10, 0)])
def test_duration_range_rejects_invalid_numbers(duration, step):
    with pytest.raises(ValueError):
        every_n_minutes_for_duration("12:00", duration, step)


@pytest.mark.parametrize(
    ("before", "after", "step", "expected"),
    [
        (60, 60, 30, ["11:00", "11:30", "12:00", "12:30", "13:00"]),
        (45, 45, 30, ["11:15", "11:45", "12:15", "12:45"]),
        (0, 0, 15, ["12:00"]),
    ],
)
def test_centered_time_range(before, after, step, expected):
    assert centered_time_range("12:00", before, after, step) == expected


@pytest.mark.parametrize(
    ("before", "after", "step"),
    [(-1, 60, 15), (60, -1, 15), (60, 60, 0)],
)
def test_centered_range_rejects_invalid_numbers(before, after, step):
    with pytest.raises(ValueError):
        centered_time_range("12:00", before, after, step)


def test_expanded_replicates_must_not_overlap():
    with pytest.raises(ScheduleValidationError, match="duplicate"):
        validate_unique_expanded_times(
            times=["09:00", "09:01"],
            replicates=2,
            replicate_interval_seconds=60,
        )


def test_write_schedule_creates_expected_json(tmp_path):
    output = tmp_path / "nested" / "schedule.json"

    write_schedule(
        output=output,
        start_date="2026-07-18",
        num_days=2,
        times=["09:00", "10:00"],
        replicates=2,
        replicate_interval_seconds=15,
    )

    assert json.loads(output.read_text()) == {
        "start_date": "2026-07-18",
        "num_days": 2,
        "replicates": 2,
        "replicate_interval_seconds": 15,
        "times": ["09:00", "10:00"],
    }
    assert list(output.parent.iterdir()) == [output]


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "18-07-2026"},
        {"num_days": 0},
        {"replicates": 0},
        {"replicate_interval_seconds": -1},
    ],
)
def test_write_schedule_rejects_invalid_metadata(tmp_path, overrides):
    arguments = {
        "output": tmp_path / "schedule.json",
        "start_date": "2026-07-18",
        "num_days": 1,
        "times": ["09:00"],
        "replicates": 1,
        "replicate_interval_seconds": 0,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError):
        write_schedule(**arguments)


def test_write_schedule_requires_explicit_overwrite(tmp_path):
    output = tmp_path / "schedule.json"
    output.write_text("original")
    arguments = {
        "output": output,
        "start_date": "2026-07-18",
        "num_days": 1,
        "times": ["09:00"],
    }

    with pytest.raises(FileExistsError):
        write_schedule(**arguments)

    write_schedule(**arguments, overwrite=True)
    assert json.loads(output.read_text())["times"] == ["09:00"]
