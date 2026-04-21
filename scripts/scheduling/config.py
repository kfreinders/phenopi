from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SchedulerConfig:
    config_path: Path
    state_path: Path
    capture_script: str
    python_bin: str
    max_lateness: timedelta
    poll_interval: float
    tz: ZoneInfo


def default_scheduler_config() -> SchedulerConfig:
    return SchedulerConfig(
        config_path=Path("/home/phenopi/phenotyping/schedule.json"),
        state_path=Path("/home/phenopi/phenotyping/completed_jobs.json"),
        capture_script="/home/phenopi/phenotyping/capture_once.py",
        python_bin="/home/phenopi/venvs/phenopi/bin/python",
        max_lateness=timedelta(minutes=10),
        poll_interval=20.0,
        tz=ZoneInfo("Europe/Amsterdam"),
    )
