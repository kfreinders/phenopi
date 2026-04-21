from __future__ import annotations

from .config import default_scheduler_config
from .scheduler import main


if __name__ == "__main__":
    main(default_scheduler_config())
