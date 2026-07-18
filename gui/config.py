from __future__ import annotations

import os
from pathlib import Path

from fastapi.templating import Jinja2Templates


APP_DIR = Path(__file__).resolve().parent


def get_project_root() -> Path:
    env_root = os.environ.get("PHENOPI_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    return APP_DIR.parent


PROJECT_ROOT = get_project_root()

DEFAULT_SCHEDULE_PATH = PROJECT_ROOT / "runtime" / "schedule.json"
SCHEDULER_HEARTBEAT_PATH = (
    PROJECT_ROOT / "runtime" / "scheduler-heartbeat.json"
)

templates = Jinja2Templates(directory=APP_DIR / "templates")
