from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(config_path: Path) -> dict[str, Any]:
    """
    Load a scheduler configuration from a JSON file.

    The configuration defines the start date, number of days, and capture
    times used to construct the schedule.

    Parameters
    ----------
    config_path : Path
        Path to the JSON configuration file.

    Returns
    -------
    dict[str, Any]
        Parsed configuration dictionary.

    Raises
    ------
    RuntimeError
        If the file does not exist or cannot be parsed as valid JSON.
    """
    try:
        return json.loads(config_path.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Schedule config not found: {config_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in config file: {config_path}"
        ) from exc


def load_completed_jobs(state_path: Path) -> set[str]:
    """
    Load previously completed job timestamps from a JSON file.

    The file is expected to contain a list of ISO-formatted datetime strings.
    If the file is missing or malformed, an empty set is returned.

    Parameters
    ----------
    state_path : Path
        Path to the JSON file storing completed job timestamps.

    Returns
    -------
    set[str]
        Set of ISO-formatted datetime strings representing completed jobs.
    """
    if not state_path.exists():
        return set()

    try:
        data = json.loads(state_path.read_text())
        if not isinstance(data, list):
            return set()
        return {str(item) for item in data}
    except Exception:
        return set()


def save_completed_jobs(state_path: Path, completed: set[str]) -> None:
    """
    Save completed job timestamps to a JSON file.

    The timestamps are written as a sorted list of ISO-formatted strings.
    The write is performed atomically via a temporary file to avoid corruption.

    Parameters
    ----------
    state_path : Path
        Path to the JSON file where completed jobs are stored.
    completed : set[str]
        Set of ISO-formatted datetime strings representing completed jobs.
    """
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(sorted(completed), indent=2))
    tmp_path.replace(state_path)
