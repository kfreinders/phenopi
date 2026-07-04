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
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from .config import SchedulerConfig, default_scheduler_config
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


def run_capture(config: SchedulerConfig) -> None:
    """
    Execute the capture script as a subprocess.

    This function invokes the configured Python interpreter to run the capture
    script once. A non-zero exit code raises `CalledProcessError`, allowing
    APScheduler to mark the job as failed.

    Parameters
    ----------
    config : SchedulerConfig
        Scheduler configuration containing the Python interpreter, capture
        script, and output directory.

    Raises
    ------
    subprocess.CalledProcessError
        If the capture script exits with a non-zero return code.
    """
    subprocess.run(
        [
            str(config.python_bin),
            str(config.capture_script),
            "--output-dir",
            str(config.output_dir),
        ],
        check=True,
    )


def make_scheduler(config: SchedulerConfig) -> BlockingScheduler:
    """
    Create an APScheduler instance with a persistent SQLite job store.

    Parameters
    ----------
    config : SchedulerConfig
        Scheduler configuration.

    Returns
    -------
    BlockingScheduler
        Configured blocking scheduler.
    """
    config.jobstore_path.parent.mkdir(parents=True, exist_ok=True)

    jobstores = {
        "default": SQLAlchemyJobStore(
            url=f"sqlite:///{config.jobstore_path}"
        )
    }

    return BlockingScheduler(
        timezone=config.tz,
        jobstores=jobstores,
    )


def format_datetime(value: datetime) -> str:
    """
    Format a datetime for scheduler log messages.

    Parameters
    ----------
    value : datetime
        Datetime to format.

    Returns
    -------
    str
        Human-readable datetime string.
    """
    return value.strftime("%Y-%m-%d %H:%M:%S %Z")


def print_startup_summary(
    config: SchedulerConfig,
    schedule_hash: str,
    run_times: list[datetime],
    scheduled: int,
    skipped_late: int,
    jobstore_existed: bool,
) -> None:
    """
    Print a user-facing summary of scheduler startup.

    Parameters
    ----------
    config : SchedulerConfig
        Scheduler configuration.
    schedule_hash : str
        SHA-256 hash of the loaded schedule file.
    run_times : list[datetime]
        All configured capture datetimes.
    scheduled : int
        Number of capture jobs added to APScheduler.
    skipped_late : int
        Number of configured captures skipped because they were too far in the
        past.
    jobstore_existed : bool
        Whether the persistent APScheduler job store already existed before
        startup.
    """
    print(f"[scheduler] Loaded schedule: {config.schedule_path}")
    print(f"[scheduler] Schedule hash: {schedule_hash}")
    print(f"[scheduler] Job store: {config.jobstore_path}")

    if jobstore_existed:
        print("[scheduler] Existing job store found; resuming scheduler state")
    else:
        print("[scheduler] No existing job store found; creating a new one")

    print(f"[scheduler] Configured capture jobs: {len(run_times)}")
    print(f"[scheduler] Scheduled pending jobs: {scheduled}")

    if skipped_late:
        print(
            "[scheduler] Skipped "
            f"{skipped_late} capture job(s) older than the misfire grace window"
        )

    if scheduled == 0:
        if run_times:
            print(
                "[scheduler] No pending capture jobs remain. "
                "The configured schedule appears to be complete or entirely in "
                "the past."
            )
        else:
            print("[scheduler] No capture jobs were found in the schedule.")
        return

    pending = [
        run_time
        for run_time in run_times
        if run_time >= datetime.now(config.tz) - config.misfire_grace
    ]

    if pending:
        print(f"[scheduler] Next capture: {format_datetime(pending[0])}")
        print(f"[scheduler] Last capture: {format_datetime(pending[-1])}")


def config_from_args(args: argparse.Namespace) -> SchedulerConfig:
    default = default_scheduler_config()

    return SchedulerConfig(
        schedule_path=args.schedule or default.schedule_path,
        state_path=default.state_path,
        capture_script=args.capture_script or default.capture_script,
        python_bin=args.python_bin or default.python_bin,
        output_dir=args.output_dir or default.output_dir,
        jobstore_path=args.jobstore_path or default.jobstore_path,
        misfire_grace=(
            timedelta(seconds=args.misfire_grace_seconds)
            if args.misfire_grace_seconds is not None
            else default.misfire_grace
        ),
        reload_interval=(
            timedelta(seconds=args.reload_interval_seconds)
            if args.reload_interval_seconds is not None
            else default.reload_interval
        ),
        tz=ZoneInfo(args.timezone) if args.timezone else default.tz,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", type=Path)
    parser.add_argument("--capture-script", type=Path)
    parser.add_argument("--python-bin", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--jobstore-path", type=Path)
    parser.add_argument("--timezone")
    parser.add_argument("--misfire-grace-seconds", type=int)
    parser.add_argument("--reload-interval-seconds", type=float)

    args = parser.parse_args()
    config = config_from_args(args)

    tz = config.tz

    try:
        schedule_hash = schedule_content_hash(config.schedule_path)
        cfg = load_schedule(config.schedule_path)
        run_times = expand_schedule(cfg, tz)
    except (
        ScheduleValidationError, ValueError, FileNotFoundError, OSError
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    jobstore_existed = config.jobstore_path.exists()
    scheduler = make_scheduler(config)

    now = datetime.now(tz)
    scheduled = 0
    skipped_late = 0

    for run_time in run_times:
        if run_time < now - config.misfire_grace:
            skipped_late += 1
            continue

        scheduler.add_job(
            run_capture,
            trigger="date",
            run_date=run_time,
            args=[config],
            id=f"{CAPTURE_JOB_PREFIX}{run_time.isoformat()}",
            misfire_grace_time=int(config.misfire_grace.total_seconds()),
            max_instances=1,
            replace_existing=True,
        )
        scheduled += 1

    print_startup_summary(
        config=config,
        schedule_hash=schedule_hash,
        run_times=run_times,
        scheduled=scheduled,
        skipped_late=skipped_late,
        jobstore_existed=jobstore_existed,
    )

    print("[scheduler] Starting scheduler")
    scheduler.start()


if __name__ == "__main__":
    main()
