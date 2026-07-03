from __future__ import annotations

import argparse
from datetime import datetime, timedelta


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

    Examples
    --------
    >>> every_n_minutes("09:00", "10:00", 30)
    ['09:00', '09:30', '10:00']

    The end time is only included if it falls exactly on a step.

    >>> every_n_minutes("09:00", "09:45", 30)
    ['09:00', '09:30']
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

    Examples
    --------
    >>> every_n_minutes_for_duration("12:00", 60, 20)
    ['12:00', '12:20', '12:40', '13:00']

    The final time is omitted if the duration is not reached exactly by
    stepping.

    >>> every_n_minutes_for_duration("12:00", 45, 20)
    ['12:00', '12:20', '12:40']
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


def centered_time_range(
    center: str,
    before_minutes: int,
    after_minutes: int,
    step_minutes: int,
) -> list[str]:
    """
    Generate capture times around a central time point.

    This is useful for creating a denser acquisition window around a treatment,
    watering event, stress application, or calibration time.

    Parameters
    ----------
    center : str
        Central time in 24-hour "HH:MM" format.
    before_minutes : int
        Number of minutes before `center` to include. Must be greater than or
        equal to 0.
    after_minutes : int
        Number of minutes after `center` to include. Must be greater than or
        equal to 0.
    step_minutes : int
        Interval between consecutive capture times, in minutes. Must be greater
        than 0.

    Returns
    -------
    list[str]
        Capture times in "HH:MM" format.

    Raises
    ------
    ValueError
        If `before_minutes` or `after_minutes` is negative, if `step_minutes`
        is not greater than 0, or if `center` is not a valid "HH:MM" string.

    Examples
    --------
    >>> centered_time_range("12:00", 60, 60, 30)
    ['11:00', '11:30', '12:00', '12:30', '13:00']

    The sequence is stepped from the calculated start time. The center is not
    forced into the output.

    >>> centered_time_range("12:00", 45, 45, 30)
    ['11:15', '11:45', '12:15', '12:45']
    """
    if before_minutes < 0:
        raise ValueError("before_minutes must be >= 0")
    if after_minutes < 0:
        raise ValueError("after_minutes must be >= 0")
    if step_minutes <= 0:
        raise ValueError("step_minutes must be > 0")

    center_dt = datetime.strptime(center, "%H:%M")
    start_dt = center_dt - timedelta(minutes=before_minutes)
    end_dt = center_dt + timedelta(minutes=after_minutes)

    times: list[str] = []
    current = start_dt

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

    Examples
    --------
    >>> combine_times(["09:00", "10:00"], ["09:30", "10:00"])
    ['09:00', '09:30', '10:00']

    Input lists do not need to be sorted.

    >>> combine_times(["10:00", "09:00"], ["09:30"])
    ['09:00', '09:30', '10:00']
    """
    return sorted({t for lst in time_lists for t in lst})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phenopi capture times and print them to stdout."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    every = subparsers.add_parser(
        "every",
        help="Generate times between a start and end time.",
    )
    every.add_argument("--start", required=True, help="Start time, HH:MM.")
    every.add_argument("--end", required=True, help="End time, HH:MM.")
    every.add_argument(
        "--step-minutes",
        type=int,
        required=True,
        help="Interval between captures in minutes.",
    )

    duration = subparsers.add_parser(
        "duration",
        help="Generate times from a start time for a fixed duration.",
    )
    duration.add_argument("--start", required=True, help="Start time, HH:MM.")
    duration.add_argument(
        "--duration-minutes",
        type=int,
        required=True,
        help="Total duration in minutes.",
    )
    duration.add_argument(
        "--step-minutes",
        type=int,
        required=True,
        help="Interval between captures in minutes.",
    )

    centered = subparsers.add_parser(
        "centered",
        help="Generate times around a central time point.",
    )
    centered.add_argument(
        "--center",
        required=True,
        help="Center time, HH:MM."
        )
    centered.add_argument(
        "--before-minutes",
        type=int,
        required=True,
        help="Minutes before center to include.",
    )
    centered.add_argument(
        "--after-minutes",
        type=int,
        required=True,
        help="Minutes after center to include.",
    )
    centered.add_argument(
        "--step-minutes",
        type=int,
        required=True,
        help="Interval between captures in minutes.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "every":
        times = every_n_minutes(
            start=args.start,
            end=args.end,
            step_minutes=args.step_minutes,
        )
    elif args.command == "duration":
        times = every_n_minutes_for_duration(
            start=args.start,
            duration_minutes=args.duration_minutes,
            step_minutes=args.step_minutes,
        )
    elif args.command == "centered":
        times = centered_time_range(
            center=args.center,
            before_minutes=args.before_minutes,
            after_minutes=args.after_minutes,
            step_minutes=args.step_minutes,
        )
    else:
        raise ValueError(f"Unknown command: {args.command}")

    print(times)


if __name__ == "__main__":
    main()
