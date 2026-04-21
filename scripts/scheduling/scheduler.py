from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import time as time_module
from typing import Callable

from .config import SchedulerConfig
from .schedule_builder import (
    build_schedule,
    load_config,
    load_completed_jobs,
    save_completed_jobs,
)


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


def process_jobs(
    jobs: list[datetime],
    completed: set[str],
    now: datetime,
    max_lateness: timedelta,
    run_capture_fn: Callable[[], bool],
) -> bool:
    """
    Execute due jobs and update completion state.

    Iterates over scheduled job times and executes any jobs that:
    - have not yet been completed, and
    - fall within the allowed execution window defined by `max_lateness`.

    Successfully executed jobs are recorded in the `completed` set.

    Parameters
    ----------
    jobs : list[datetime]
        List of scheduled job datetimes.
    completed : set[str]
        Set of ISO-formatted datetime strings representing already completed
        jobs. This set is modified in place.
    now : datetime
        Current time against which job execution eligibility is evaluated.
    max_lateness : timedelta
        Maximum allowed delay after the scheduled job time during which the
        job may still be executed.
    run_capture_fn : Callable[[], bool]
        Callable that performs the capture action and returns True on success.

    Returns
    -------
    bool
        True if the completion state was modified (i.e. one or more jobs were
        executed successfully), False otherwise.
    """
    state_changed = False

    for job_time in jobs:
        job_key = job_time.isoformat()

        if job_key in completed:
            continue

        if job_time <= now <= job_time + max_lateness:
            print(f"[scheduler] Running job scheduled at {job_key}")

            if run_capture_fn():
                print(f"[scheduler] SUCCESS {job_key}")
                completed.add(job_key)
                state_changed = True
            else:
                print(f"[scheduler] FAILED {job_key}")

        elif now > job_time + max_lateness:
            print(f"[scheduler] SKIPPED (too late) {job_key}")
            completed.add(job_key)
            state_changed = True

    return state_changed


def run_once(
    scheduler_config: SchedulerConfig,
    completed: set[str],
    now: datetime,
) -> bool:
    """
    Perform a single scheduler iteration.

    Loads the schedule configuration, constructs the job list, and processes
    any jobs that are due at the given time. If new jobs are completed, the
    updated state is persisted to disk.

    Parameters
    ----------
    scheduler_config : SchedulerConfig
        Configuration containing file paths, timing parameters, and execution
        settings for the scheduler.
    completed : set[str]
        Set of ISO-formatted datetime strings representing completed jobs.
        This set is modified in place.
    now : datetime
        Current time used to determine which jobs are due.

    Returns
    -------
    bool
        True if the completion state was updated and written to disk, False
        otherwise.
    """
    cfg = load_config(scheduler_config.config_path)
    jobs = build_schedule(cfg, scheduler_config.tz)

    state_changed = process_jobs(
        jobs=jobs,
        completed=completed,
        now=now,
        max_lateness=scheduler_config.max_lateness,
        run_capture_fn=lambda: run_capture(
            scheduler_config.python_bin,
            scheduler_config.capture_script,
            scheduler_config.output_dir
        ),
    )

    if state_changed:
        save_completed_jobs(scheduler_config.state_path, completed)

    return state_changed


def main(scheduler_config: SchedulerConfig) -> None:
    """
    Run the scheduler loop indefinitely.

    This function initializes the completed job state and continuously polls
    for due jobs at a fixed interval. Each iteration attempts to execute any
    eligible jobs and handles errors gracefully without terminating the loop.

    Parameters
    ----------
    scheduler_config : SchedulerConfig
        Configuration containing file paths, timing parameters, and execution
        settings for the scheduler.
    """
    completed = load_completed_jobs(scheduler_config.state_path)

    while True:
        try:
            now = datetime.now(scheduler_config.tz)
            run_once(
                scheduler_config=scheduler_config,
                completed=completed,
                now=now,
            )
        except Exception as exc:
            print(f"[scheduler] {exc}")

        time_module.sleep(scheduler_config.poll_interval)
