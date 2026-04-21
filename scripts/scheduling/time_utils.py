from __future__ import annotations

from datetime import datetime, time, timedelta


def parse_hhmm(value: str) -> time:
    """
    Parse a time string in "HH:MM" format.

    This helper converts a 24-hour clock string such as "09:30" into a
    `datetime.time` object.

    Parameters
    ----------
    value : str
        Time string in 24-hour "HH:MM" format.

    Returns
    -------
    time
        Parsed time value.

    Raises
    ------
    ValueError
        If `value` is not a valid time string in "HH:MM" format.
    """
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(
            f"Invalid time format '{value}', expected HH:MM"
        ) from exc


def every_n_minutes(start: str, end: str, step_minutes: int) -> list[str]:
    """
    Generate times at a fixed interval between two clock times.

    The returned list includes both the start time and, if reached exactly by
    stepping, the end time. All times are formatted as "HH:MM".

    Parameters
    ----------
    start : str
        Start time in 24-hour "HH:MM" format.
    end : str
        End time in 24-hour "HH:MM" format.
    step_minutes : int
        Interval between consecutive times, in minutes. Must be greater than 0.

    Returns
    -------
    list[str]
        Sorted list of time strings from `start` to `end`, inclusive where
        applicable.

    Raises
    ------
    ValueError
        If `step_minutes` is not greater than 0, or if `start` or `end` are not
        valid "HH:MM" strings.
    """
    if step_minutes <= 0:
        raise ValueError("step_minutes must be > 0")

    times: list[str] = []
    current = datetime.strptime(start, "%H:%M")
    end_dt = datetime.strptime(end, "%H:%M")

    while current <= end_dt:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=step_minutes)

    return times


def every_n_minutes_for_duration(
    start: str,
    duration_minutes: int,
    step_minutes: int,
) -> list[str]:
    """
    Generate times at a fixed interval starting from a given time and duration.

    The returned list starts at `start` and continues in steps of
    `step_minutes` until the specified duration has been covered. The start
    time is always included, and the final time is included if it falls exactly
    on a step.

    Parameters
    ----------
    start : str
        Start time in 24-hour "HH:MM" format.
    duration_minutes : int
        Total duration to cover, in minutes. Must be greater than or equal to
        0.
    step_minutes : int
        Interval between consecutive times, in minutes. Must be greater than 0.

    Returns
    -------
    list[str]
        List of time strings in "HH:MM" format spanning the requested duration.

    Raises
    ------
    ValueError
        If `duration_minutes` is negative.
    ValueError
        If `step_minutes` is not greater than 0, or if `start` is not a valid
        "HH:MM" string.
    """
    if duration_minutes < 0:
        raise ValueError("duration_minutes must be >= 0")
    if step_minutes <= 0:
        raise ValueError("step_minutes must be > 0")

    times: list[str] = []
    current = datetime.strptime(start, "%H:%M")
    end_dt = current + timedelta(minutes=duration_minutes)

    while current <= end_dt:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=step_minutes)

    return times


def combine_times(*time_lists: list[str]) -> list[str]:
    """
    Combine multiple lists of time strings into one sorted unique list.

    Duplicate times are removed, and the result is sorted lexicographically,
    which is appropriate for zero-padded "HH:MM" strings.

    Parameters
    ----------
    time_lists : list[str]
        One or more lists of time strings in "HH:MM" format.

    Returns
    -------
    list[str]
        Sorted list of unique time strings.
    """
    return sorted({t for lst in time_lists for t in lst})
