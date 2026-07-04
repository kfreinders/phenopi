from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Hashable, TypeVar


T = TypeVar("T", bound=Hashable)


class ScheduleValidationError(ValueError):
    """
    Raised when a schedule is invalid.

    This exception is intended for user-facing schedule validation errors, such
    as duplicate capture times or invalid schedule settings. Command-line tools
    can catch this exception and report a concise error message without showing
    a full traceback.
    """


def format_duplicate_values(
    duplicates: Iterable[str],
    max_display: int = 5,
) -> str:
    """
    Format duplicate values for display in an error message.

    Parameters
    ----------
    duplicates : Iterable[str]
        Duplicate values formatted as strings.
    max_display : int, optional
        Maximum number of duplicate values to include explicitly.

    Returns
    -------
    str
        Formatted duplicate-value summary.
    """
    sorted_duplicates = sorted(duplicates)
    shown = sorted_duplicates[:max_display]

    duplicate_text = ", ".join(shown)
    remaining = len(sorted_duplicates) - len(shown)

    if remaining > 0:
        duplicate_text += f", ... ({remaining} more)"

    return duplicate_text


def validate_unique_values(
    values: Iterable[T],
    *,
    label: str = "schedule",
    value_name: str = "capture time",
    formatter: Callable[[T], str] = str,
) -> None:
    """
    Check that values are unique.

    Parameters
    ----------
    values : Iterable[T]
        Values to check for duplicates.
    label : str, optional
        Description of the object being validated.
    value_name : str, optional
        Name of the duplicated value type used in the error message.
    formatter : Callable[[T], str], optional
        Function used to format duplicate values for display.

    Raises
    ------
    ScheduleValidationError
        If duplicate values are present.
    """
    seen: set[T] = set()
    duplicates: set[T] = set()

    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)

    if not duplicates:
        return

    duplicate_text = format_duplicate_values(
        formatter(value) for value in duplicates
    )
    duplicate_count = len(duplicates)

    raise ScheduleValidationError(
        f"{label} contains {duplicate_count} duplicate {value_name}(s). "
        f"First duplicates: {duplicate_text}. This usually means "
        "that replicate captures overlap with other scheduled captures. "
        "Increase --step-minutes, reduce --replicates, or reduce "
        "--replicate-interval-seconds."
    )
