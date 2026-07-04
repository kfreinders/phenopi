from datetime import time
import pytest
from scripts.scheduling.time_utils import (
    parse_hhmm,
    every_n_minutes,
    every_n_minutes_for_duration,
    centered_time_range,
    combine_times,
)


# ---------------------------------------------------------------------------
# test_parse_hhmm
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "input_str, expected",
    [
        ("00:00", time(0, 0)),
        ("09:30", time(9, 30)),
        ("23:59", time(23, 59)),
    ],
)
def test_parse_hhmm_valid(input_str, expected):
    assert parse_hhmm(input_str) == expected


@pytest.mark.parametrize(
    "input_str",
    [
        "24:00",     # invalid hour
        "12:60",     # invalid minute
        "abc",       # nonsense
        "",          # empty
    ],
)
def test_parse_hhmm_invalid(input_str):
    with pytest.raises(ValueError):
        parse_hhmm(input_str)


# ---------------------------------------------------------------------------
# every_n_minutes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "start, end, step, expected",
    [
        ("09:00", "10:00", 30, ["09:00", "09:30", "10:00"]),
        ("09:00", "09:00", 15, ["09:00"]),
        ("09:00", "09:45", 30, ["09:00", "09:30"]),
        ("10:00", "09:00", 30, []),  # start > end
    ],
)
def test_every_n_minutes_cases(start, end, step, expected):
    assert every_n_minutes(start, end, step) == expected


@pytest.mark.parametrize(
    "step",
    [0, -1],
)
def test_every_n_minutes_invalid_step(step):
    with pytest.raises(ValueError):
        every_n_minutes("09:00", "10:00", step)


@pytest.mark.parametrize(
    "start, end",
    [
        ("abc", "10:00"),
        ("09:00", "xyz"),
        ("24:00", "10:00"),
    ],
)
def test_every_n_minutes_invalid_time_strings(start, end):
    with pytest.raises(ValueError):
        every_n_minutes(start, end, 30)


# ---------------------------------------------------------------------------
# every_n_minutes_for_duration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "start, duration, step, expected",
    [
        ("12:00", 60, 20, ["12:00", "12:20", "12:40", "13:00"]),
        ("12:00", 0, 10, ["12:00"]),
        ("12:00", 45, 20, ["12:00", "12:20", "12:40"]),
    ],
)
def test_every_n_minutes_for_duration_cases(start, duration, step, expected):
    assert every_n_minutes_for_duration(start, duration, step) == expected


@pytest.mark.parametrize(
    "duration, step",
    [
        (-1, 10),   # invalid duration
        (10, 0),    # invalid step
        (10, -5),   # invalid step
    ],
)
def test_every_n_minutes_for_duration_errors(duration, step):
    with pytest.raises(ValueError):
        every_n_minutes_for_duration("12:00", duration, step)


# ---------------------------------------------------------------------------
# centered_time_range
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "center, before, after, step, expected",
    [
        (
            "12:00",
            60,
            60,
            30,
            ["11:00", "11:30", "12:00", "12:30", "13:00"],
        ),
        (
            "12:00",
            0,
            60,
            20,
            ["12:00", "12:20", "12:40", "13:00"],
        ),
        (
            "12:00",
            60,
            0,
            20,
            ["11:00", "11:20", "11:40", "12:00"],
        ),
        (
            "12:00",
            0,
            0,
            15,
            ["12:00"],
        ),
        (
            "12:00",
            45,
            45,
            30,
            ["11:15", "11:45", "12:15", "12:45"],
        ),
    ],
)
def test_centered_time_range_cases(center, before, after, step, expected):
    assert centered_time_range(center, before, after, step) == expected


@pytest.mark.parametrize(
    "before, after, step",
    [
        (-1, 60, 15),   # invalid before
        (60, -1, 15),   # invalid after
        (60, 60, 0),    # invalid step
        (60, 60, -5),   # invalid step
    ],
)
def test_centered_time_range_invalid_arguments(before, after, step):
    with pytest.raises(ValueError):
        centered_time_range("12:00", before, after, step)


@pytest.mark.parametrize(
    "center",
    [
        "abc",
        "",
        "24:00",
        "12:60",
    ],
)
def test_centered_time_range_invalid_center(center):
    with pytest.raises(ValueError):
        centered_time_range(center, 60, 60, 15)


# ---------------------------------------------------------------------------
# combine_times
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "inputs, expected",
    [
        ((["09:00"], ["10:00"]), ["09:00", "10:00"]),
        ((["10:00", "09:00"],), ["09:00", "10:00"]),
        ((["09:00"], ["09:00"]), ["09:00"]),
        (([], ["12:00"]), ["12:00"]),
    ],
)
def test_combine_times(inputs, expected):
    assert combine_times(*inputs) == expected
