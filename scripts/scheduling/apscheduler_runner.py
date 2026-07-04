from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from .schedule_validation import (
    ScheduleValidationError,
    validate_unique_values,
)


CAPTURE_JOB_PREFIX = "capture:"
RELOAD_JOB_ID = "reload_schedule"


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


def schedule_content_hash(path: Path) -> str:
    """
    Compute a SHA-256 hash of a schedule file.

    The hash is based on the file contents, not on metadata such as filename,
    modification time, or file size. This makes it suitable for detecting
    whether the actual schedule definition has changed.

    Parameters
    ----------
    path : Path
        Path to the schedule file.

    Returns
    -------
    str
        Hexadecimal SHA-256 digest of the file contents.

    Raises
    ------
    FileNotFoundError
        If `path` does not exist.
    OSError
        If the file cannot be read.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_schedule(path: Path) -> dict:
    return json.loads(path.read_text())


def expand_schedule(cfg: dict, tz: ZoneInfo) -> list[datetime]:
    start_date = date.fromisoformat(cfg["start_date"])
    num_days = int(cfg["num_days"])
    times = sorted({parse_hhmm(t) for t in cfg["times"]})

    replicates = int(cfg.get("replicates", 1))
    replicate_interval = int(cfg.get("replicate_interval_seconds", 0))

    if num_days <= 0:
        raise ValueError("num_days must be > 0")
    if replicates <= 0:
        raise ValueError("replicates must be > 0")
    if replicate_interval < 0:
        raise ValueError("replicate_interval_seconds must be >= 0")

    jobs = []
    for day_offset in range(num_days):
        current_day = start_date + timedelta(days=day_offset)
        for capture_time in times:
            base = datetime.combine(current_day, capture_time, tzinfo=tz)
            for rep in range(replicates):
                jobs.append(base + timedelta(seconds=rep * replicate_interval))

    validate_unique_values(
        jobs,
        label="expanded schedule",
        value_name="capture time",
        formatter=lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S%z"),
    )

    return sorted(jobs)


def run_capture(
    python_bin: str,
    capture_script: str,
    output_dir: Path
) -> bool:
    """
    Execute the capture script as a subprocess.

    This function invokes the configured Python interpreter to run the
    capture script once and returns whether execution was successful.

    Parameters
    ----------
    python_bin : str
        Path to the Python executable used to run the capture script.
    capture_script : str
        Path to the capture script to execute.
    output_dir : Path
        Path to save the capture script output to.

    Returns
    -------
    bool
        True if the capture script exited with return code 0, False otherwise.
    """
    result = subprocess.run(
        [
            python_bin,
            capture_script,
            "--output-dir",
            str(output_dir),
        ],
        check=False
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--capture-script", type=str, required=True)
    parser.add_argument("--python-bin", type=str, default="python")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timezone", default="Europe/Amsterdam")
    parser.add_argument("--misfire-grace-seconds", type=int, default=600)
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)

    try:
        cfg = load_schedule(args.schedule)
        run_times = expand_schedule(cfg, tz)
    except (
        ScheduleValidationError, ValueError, FileNotFoundError, OSError
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    scheduler = BlockingScheduler(timezone=tz)

    now = datetime.now(tz)
    scheduled = 0

    for i, run_time in enumerate(run_times):
        if run_time < now - timedelta(seconds=args.misfire_grace_seconds):
            continue

        scheduler.add_job(
            run_capture,
            trigger="date",
            run_date=run_time,
            args=[args.python_bin, args.capture_script, args.output_dir],
            id=f"capture_{i}_{run_time.isoformat()}",
            misfire_grace_time=args.misfire_grace_seconds,
            max_instances=1,
        )
        scheduled += 1

    print(f"Scheduled {scheduled} capture job(s)")
    print("Starting scheduler")

    scheduler.start()


if __name__ == "__main__":
    main()
