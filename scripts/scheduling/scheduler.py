from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import time as time_module
import sys
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler

from .config import SchedulerConfig, default_scheduler_config
from .heartbeat import HEARTBEAT_INTERVAL_SECONDS, SchedulerHeartbeat
from .schedule_validation import (
    ScheduleValidationError,
    validate_unique_values,
)


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


def build_schedule_snapshot(
    cfg: dict,
    schedule_hash: str,
    tz: ZoneInfo,
) -> dict:
    """Build the normalized schedule metadata published in the heartbeat."""
    return {
        "hash": schedule_hash,
        "timezone": getattr(tz, "key", str(tz)),
        "start_date": date.fromisoformat(cfg["start_date"]).isoformat(),
        "num_days": int(cfg["num_days"]),
        "times": sorted(
            {
                parse_hhmm(value).strftime("%H:%M")
                for value in cfg["times"]
            }
        ),
        "replicates": int(cfg.get("replicates", 1)),
        "replicate_interval_seconds": int(
            cfg.get("replicate_interval_seconds", 0)
        ),
    }


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


def record_capture_event(
    event,
    heartbeat: SchedulerHeartbeat,
    schedule_hash: str,
) -> None:
    """Record the latest capture result from an APScheduler job event."""
    if not event.job_id.startswith("capture_"):
        return
    if event.code == EVENT_JOB_EXECUTED:
        status = "succeeded"
        message = "Capture completed successfully."
    elif event.code == EVENT_JOB_MISSED:
        status = "missed"
        message = "Capture was missed by the scheduler."
    else:
        status = "failed"
        message = str(event.exception) if event.exception else "Capture failed."
    heartbeat.record_capture(
        {
            "schedule_hash": schedule_hash,
            "status": status,
            "scheduled_at": event.scheduled_run_time.isoformat(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }
    )


def make_scheduler(
    config: SchedulerConfig,
    jobstore_path: Path,
) -> BlockingScheduler:
    """
    Create an APScheduler instance with persistent capture jobs.

    Capture jobs are stored in a SQLite job store. Internal control jobs, such
    as schedule polling, are stored in memory so that they are not persisted
    into the schedule-specific database.

    Parameters
    ----------
    config : SchedulerConfig
        Scheduler configuration.
    jobstore_path : Path
        SQLite database path used for capture jobs.

    Returns
    -------
    BlockingScheduler
        Configured blocking scheduler.
    """
    jobstore_path.parent.mkdir(parents=True, exist_ok=True)

    jobstores = {
        "default": SQLAlchemyJobStore(
            url=f"sqlite:///{jobstore_path}"
        ),
        "control": MemoryJobStore(),
    }

    return BlockingScheduler(
        timezone=config.tz,
        jobstores=jobstores,
    )


def poll_schedule_for_changes(
    scheduler: BlockingScheduler,
    config: SchedulerConfig,
    active_schedule_hash: str,
    heartbeat: SchedulerHeartbeat | None = None,
) -> None:
    """
    Check whether the schedule file has changed.

    If the schedule hash is unchanged, the current scheduler continues running.
    If the schedule hash has changed and the new schedule is valid, the current
    scheduler is shut down. The outer service loop can then restart the
    scheduler using the new schedule hash and matching SQLite job store.

    Parameters
    ----------
    scheduler : BlockingScheduler
        Running scheduler instance.
    config : SchedulerConfig
        Scheduler configuration.
    active_schedule_hash : str
        Schedule hash used to initialize the current scheduler.
    """
    try:
        current_hash = schedule_content_hash(config.schedule_path)

        if current_hash == active_schedule_hash:
            if heartbeat is not None:
                heartbeat.set_state(
                    "running",
                    "The scheduler is running with a valid schedule.",
                )
            return

        cfg = load_schedule(config.schedule_path)
        expand_schedule(cfg, config.tz)

    except (
        ScheduleValidationError,
        KeyError,
        TypeError,
        ValueError,
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        if heartbeat is not None:
            heartbeat.set_state(
                "invalid_schedule",
                f"The updated schedule is invalid; keeping the active schedule: {exc}",
            )
        print(
            "[scheduler] Schedule file changed or could not be read, but the "
            f"new schedule is not valid: {exc}. Keeping current schedule."
        )
        return

    print(
        "[scheduler] Schedule file changed and the new schedule is valid. "
        "Restarting scheduler with the new schedule database."
    )
    if heartbeat is not None:
        heartbeat.set_state(
            "running",
            "A valid schedule update was found; reloading the scheduler.",
        )
    scheduler.shutdown(wait=False)


def jobstore_path_for_schedule(
    runtime_dir: Path,
    schedule_hash: str,
    hash_length: int = 12,
) -> Path:
    """
    Build the APScheduler SQLite job store path for a schedule hash.

    Parameters
    ----------
    runtime_dir : Path
        Directory where runtime files are stored.
    schedule_hash : str
        SHA-256 hash of the schedule file contents.
    hash_length : int, optional
        Number of hash characters to include in the filename.

    Returns
    -------
    Path
        SQLite job store path for the schedule.
    """
    short_hash = schedule_hash[:hash_length]
    return runtime_dir / f"apscheduler-{short_hash}.sqlite"


def run_scheduler_until_reload(
    config: SchedulerConfig,
    heartbeat: SchedulerHeartbeat | None = None,
) -> bool:
    """
    Start APScheduler for the current schedule.

    The function returns ``True`` after a scheduler was started and later shut
    down. It returns ``False`` when no valid schedule could be loaded, allowing
    the outer service loop to remain alive and retry.
    """
    tz = config.tz

    try:
        schedule_hash = schedule_content_hash(config.schedule_path)
        jobstore_path = jobstore_path_for_schedule(
            runtime_dir=config.runtime_dir,
            schedule_hash=schedule_hash,
        )
        jobstore_existed = jobstore_path.exists()

        stale_deleted = delete_stale_jobstores(
            runtime_dir=config.runtime_dir,
            current_jobstore_path=jobstore_path,
        )

        cfg = load_schedule(config.schedule_path)
        run_times = expand_schedule(cfg, tz)
    except FileNotFoundError:
        if heartbeat is not None:
            heartbeat.set_state(
                "waiting_for_schedule",
                "The scheduler is waiting for a schedule file.",
                schedule=None,
            )
        print(
            "[scheduler] Schedule file disappeared before it could be loaded. "
            "Waiting for schedule..."
        )
        return False
    except (
        ScheduleValidationError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        error_message = describe_schedule_load_error(exc)
        if heartbeat is not None:
            heartbeat.set_state(
                "invalid_schedule",
                f"The scheduler could not load the schedule: {error_message}",
                schedule=None,
            )
        print(
            f"[scheduler] Invalid schedule: {error_message}",
            flush=True,
        )
        return False

    scheduler = make_scheduler(config, jobstore_path)

    if heartbeat is not None:
        scheduler.add_listener(
            lambda event: record_capture_event(
                event,
                heartbeat,
                schedule_hash,
            ),
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )

    scheduler.add_job(
        poll_schedule_for_changes,
        trigger="interval",
        seconds=config.reload_interval.total_seconds(),
        args=[scheduler, config, schedule_hash, heartbeat],
        id="poll_schedule",
        max_instances=1,
        replace_existing=True,
        jobstore="control",
    )

    if heartbeat is not None:
        heartbeat.set_state(
            "running",
            "The scheduler is running with a valid schedule.",
            schedule=build_schedule_snapshot(cfg, schedule_hash, tz),
        )
        scheduler.add_job(
            heartbeat.write,
            trigger="interval",
            seconds=HEARTBEAT_INTERVAL_SECONDS,
            id="write_heartbeat",
            max_instances=1,
            replace_existing=True,
            jobstore="control",
        )

    now = datetime.now(tz)
    scheduled = 0
    skipped_past = 0

    for run_time in run_times:
        if run_time < now:
            skipped_past += 1
            continue

        scheduler.add_job(
            run_capture,
            trigger="date",
            run_date=run_time,
            args=[config],
            id=f"capture_{run_time.isoformat()}",
            misfire_grace_time=int(config.misfire_grace.total_seconds()),
            max_instances=1,
            replace_existing=True,
        )
        scheduled += 1

    print_startup_summary(
        config=config,
        schedule_hash=schedule_hash,
        jobstore_path=jobstore_path,
        run_times=run_times,
        scheduled=scheduled,
        skipped_late=skipped_past,
        jobstore_existed=jobstore_existed,
        stale_deleted=stale_deleted,
    )

    print("[scheduler] Starting scheduler")
    scheduler.start()
    return True


def wait_for_schedule(
    config: SchedulerConfig,
    heartbeat: SchedulerHeartbeat | None = None,
) -> None:
    """
    Wait until the configured schedule file exists.

    This is used when the scheduler service starts before an experiment
    schedule has been created. The service remains active and periodically
    checks for the schedule file.
    """
    interval_seconds = min(
        config.reload_interval.total_seconds(),
        HEARTBEAT_INTERVAL_SECONDS,
    )

    while not config.schedule_path.exists():
        if heartbeat is not None:
            heartbeat.set_state(
                "waiting_for_schedule",
                "The scheduler is waiting for a schedule file.",
                schedule=None,
            )
        print(
            "[scheduler] No schedule file found at "
            f"{config.schedule_path}. Waiting for schedule..."
        )
        time_module.sleep(interval_seconds)


def describe_schedule_load_error(exc: Exception) -> str:
    """Turn low-level schedule parsing failures into actionable messages."""
    if isinstance(exc, json.JSONDecodeError):
        if not exc.doc.strip():
            return "The schedule file is empty."
        return (
            "The schedule file does not contain valid JSON "
            f"(line {exc.lineno}, column {exc.colno})."
        )
    if isinstance(exc, KeyError):
        return f"The schedule is missing required field {exc.args[0]!r}."
    return str(exc)


def delete_stale_jobstores(
    runtime_dir: Path,
    current_jobstore_path: Path,
) -> int:
    """
    Delete APScheduler SQLite stores that do not match the current schedule.

    Job stores are named from the schedule hash. Any matching database in
    `runtime_dir` that is not the current job store is considered stale and is
    removed.

    Parameters
    ----------
    runtime_dir : Path
        Directory containing scheduler runtime files.
    current_jobstore_path : Path
        SQLite job store path for the currently loaded schedule.

    Returns
    -------
    int
        Number of stale job store files deleted.

    Raises
    ------
    OSError
        If a stale job store cannot be deleted.
    """
    if not runtime_dir.exists():
        return 0

    current_jobstore_path = current_jobstore_path.resolve()
    deleted = 0

    for path in runtime_dir.glob("apscheduler-*.sqlite"):
        if path.resolve() == current_jobstore_path:
            continue

        path.unlink()
        deleted += 1

    return deleted


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
    jobstore_path: Path,
    run_times: list[datetime],
    scheduled: int,
    skipped_late: int,
    jobstore_existed: bool,
    stale_deleted: int,
) -> None:
    """
    Print a user-facing summary of scheduler startup.

    Parameters
    ----------
    config : SchedulerConfig
        Scheduler configuration.
    schedule_hash : str
        SHA-256 hash of the loaded schedule file.
    jobstore_path : Path
        SQLite job store path used for this schedule.
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
    print(f"[scheduler] Job store: {jobstore_path}")

    if jobstore_existed:
        print(
            "[scheduler] Matching job store found for this schedule; "
            "resuming pending jobs"
        )
    else:
        print(
            "[scheduler] No matching job store found for this schedule; "
            "creating a new scheduler database"
        )

    if stale_deleted:
        print(
            f"[scheduler] Deleted {stale_deleted} stale scheduler database(s)"
        )

    print(f"[scheduler] Configured capture jobs: {len(run_times)}")
    print(f"[scheduler] Scheduled pending jobs: {scheduled}")

    if skipped_late:
        print(
            f"[scheduler] Skipped {skipped_late} capture job(s) older than"
            "the misfire grace window"
        )

    if scheduled == 0:
        if run_times:
            print(
                "[scheduler] No pending capture jobs remain. "
                "The configured schedule appears to be complete or entirely "
                "in the past."
            )
        else:
            print("[scheduler] No capture jobs were found in the schedule.")

        print(
            "[scheduler] Scheduler will remain active and continue watching "
            "for schedule changes."
        )
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
        capture_script=args.capture_script or default.capture_script,
        python_bin=args.python_bin or default.python_bin,
        output_dir=args.output_dir or default.output_dir,
        runtime_dir=args.runtime_dir or default.runtime_dir,
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
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--timezone")
    parser.add_argument("--misfire-grace-seconds", type=int)
    parser.add_argument("--reload-interval-seconds", type=float)

    args = parser.parse_args()
    config = config_from_args(args)
    heartbeat = SchedulerHeartbeat(
        config.runtime_dir,
        storage_path=config.output_dir,
    )

    while True:
        try:
            wait_for_schedule(config, heartbeat)
            scheduler_started = run_scheduler_until_reload(config, heartbeat)
        except KeyboardInterrupt:
            print("[scheduler] Stopping scheduler")
            raise SystemExit(0) from None

        if not scheduler_started:
            retry_seconds = min(
                config.reload_interval.total_seconds(),
                HEARTBEAT_INTERVAL_SECONDS,
            )
            print(
                f"[scheduler] Retrying schedule load in {retry_seconds:g} seconds",
                flush=True,
            )
            time_module.sleep(retry_seconds)
            continue
        print("[scheduler] Scheduler stopped; reloading schedule")


if __name__ == "__main__":
    main()
