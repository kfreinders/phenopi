from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler


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

    return sorted(jobs)


def run_capture(
    python_bin: str,
    capture_script: str,
    output_dir: Path
) -> None:
    subprocess.run(
        [
            python_bin,
            capture_script,
            "--output-dir",
            str(output_dir),
        ],
        check=True,
    )


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
    cfg = load_schedule(args.schedule)
    run_times = expand_schedule(cfg, tz)

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
