from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.scheduling.schedule_builder import build_schedule


TZ = ZoneInfo("Europe/Amsterdam")


@pytest.mark.parametrize(
    "cfg, error_match",
    [
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
            },
            "Missing required config key",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": 0,
                "times": ["09:00"],
            },
            "num_days must be > 0",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": -1,
                "times": ["09:00"],
            },
            "num_days must be > 0",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": "09:00",
            },
            "times must be a non-empty list of HH:MM strings",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": 123,
            },
            "times must be a non-empty list of HH:MM strings",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": None,
            },
            "times must be a non-empty list of HH:MM strings",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": [],
            },
            "times must be a non-empty list of HH:MM strings",
        ),
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": ["09:00", "abc"],
            },
            "Invalid time format",
        ),
    ],
    ids=[
        "missing-required-key",
        "num-days-zero",
        "num-days-negative",
        "times-string-not-list",
        "times-int-not-list",
        "times-none-not-list",
        "times-empty-list",
        "invalid-time-string",
    ],
)
def test_build_schedule_invalid_inputs(cfg, error_match):
    with pytest.raises(ValueError, match=error_match):
        build_schedule(cfg, TZ)


@pytest.mark.parametrize(
    "cfg, expected",
    [
        (
            {
                "start_date": "2026-04-21",
                "num_days": 1,
                "times": ["15:00", "09:00", "09:00"],
            },
            [
                datetime(2026, 4, 21, 9, 0, tzinfo=TZ),
                datetime(2026, 4, 21, 15, 0, tzinfo=TZ),
            ],
        ),
    ],
    ids=[
        "deduplicates-and-sorts-times",
    ],
)
def test_build_schedule_valid_outputs(cfg, expected):
    result = build_schedule(cfg, TZ)

    assert result == expected
