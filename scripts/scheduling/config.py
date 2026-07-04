from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SchedulerConfig:
    schedule_path: Path
    capture_script: Path
    python_bin: Path
    output_dir: Path
    runtime_dir: Path
    misfire_grace: timedelta
    reload_interval: timedelta
    tz: ZoneInfo


def default_scheduler_config() -> SchedulerConfig:
    wd = Path(
        "/home/phenopi/phenopi/"
    )
    return SchedulerConfig(
        schedule_path=wd / "runtime/schedule.json",
        capture_script=wd / "scripts/capture/capture_once.py",
        python_bin=Path("/home/phenopi/venvs/phenopi/bin/python"),
        output_dir=wd / "captures",
        runtime_dir=wd / "runtime/",
        misfire_grace=timedelta(minutes=10),
        reload_interval=timedelta(seconds=30),
        tz=ZoneInfo("Europe/Amsterdam"),
    )
