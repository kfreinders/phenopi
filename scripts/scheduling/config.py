from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SchedulerConfig:
    config_path: Path
    state_path: Path
    capture_script: Path
    python_bin: Path
    output_dir: Path
    max_lateness: timedelta
    poll_interval: float
    tz: ZoneInfo


# def default_scheduler_config() -> SchedulerConfig:
#     return SchedulerConfig(
#         config_path=Path("/home/phenopi/phenotyping/schedule.json"),
#         state_path=Path("/home/phenopi/phenotyping/completed_jobs.json"),
#         capture_script="/home/phenopi/phenotyping/capture_once.py",
#         python_bin="/home/phenopi/venvs/phenopi/bin/python",
#         output_dir=Path("/home/phenopi/captures"),
#         max_lateness=timedelta(minutes=10),
#         poll_interval=20.0,
#         tz=ZoneInfo("Europe/Amsterdam"),
#     )


def default_scheduler_config() -> SchedulerConfig:
    testpath = Path(
        "/home/koen/Documents/MSc Biology/Y2/2b2-3_research_project_2/phenopi/"
    )
    return SchedulerConfig(
        config_path=testpath / "runtime/schedule.json",
        state_path=testpath / "runtime/completed_jobs.json",
        capture_script=testpath / "scripts/capture/dummy_capture.py",
        python_bin=Path("/home/koen/Downloads/plantcv/bin/python"),
        output_dir=testpath / "captures",
        max_lateness=timedelta(minutes=10),
        poll_interval=5.0,
        tz=ZoneInfo("Europe/Amsterdam"),
    )
