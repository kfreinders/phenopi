from zoneinfo import ZoneInfo

import pytest

from gui.services import schedule_preview
from gui.services.schedule_preview import build_schedule_preview
from scripts.scheduling.make_schedule import write_schedule
from scripts.scheduling.scheduler import expand_schedule, load_schedule


BASE_ARGUMENTS = {
    "start_date": "2026-07-18",
    "num_days": 2,
    "replicates": 2,
    "replicate_interval_seconds": 10,
    "output": "runtime/schedule.json",
    "overwrite": True,
}


@pytest.mark.parametrize(
    ("mode", "mode_arguments", "expected"),
    [
        (
            "every",
            {"every_start": "09:00", "every_end": "10:00", "every_step_minutes": 30},
            ["09:00", "09:30", "10:00"],
        ),
        (
            "duration",
            {
                "duration_start": "09:00",
                "duration_minutes": 60,
                "duration_step_minutes": 30,
            },
            ["09:00", "09:30", "10:00"],
        ),
        (
            "centered",
            {
                "centered_center": "10:00",
                "centered_before_minutes": 30,
                "centered_after_minutes": 30,
                "centered_step_minutes": 30,
            },
            ["09:30", "10:00", "10:30"],
        ),
    ],
)
def test_build_schedule_preview_modes(mode, mode_arguments, expected):
    preview = build_schedule_preview(
        **BASE_ARGUMENTS,
        mode=mode,
        **mode_arguments,
    )

    assert preview.times == expected
    assert preview.daily_captures == len(expected) * 2
    assert preview.total_captures == len(expected) * 4
    assert preview.date_range_label == "2026-07-18 → 2026-07-19"
    assert preview.replicate_offsets == [
        {"number": 1, "offset_seconds": 0},
        {"number": 2, "offset_seconds": 10},
    ]
    assert preview.as_schedule_dict()["times"] == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "18-07-2026"},
        {"num_days": 0},
        {"replicates": 0},
        {"replicate_interval_seconds": -1},
        {"mode": "unknown"},
    ],
)
def test_schedule_preview_rejects_invalid_form_values(overrides):
    arguments = {
        **BASE_ARGUMENTS,
        "mode": "every",
        "every_start": "09:00",
        "every_end": "10:00",
        "every_step_minutes": 30,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError):
        build_schedule_preview(**arguments)


def test_schedule_preview_requires_fields_for_selected_mode():
    with pytest.raises(ValueError, match="Duration mode requires"):
        build_schedule_preview(**BASE_ARGUMENTS, mode="duration")


def test_resolve_output_path_preserves_absolute_and_resolves_relative(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(schedule_preview, "PROJECT_ROOT", tmp_path)

    assert schedule_preview.resolve_output_path("runtime/schedule.json") == (
        tmp_path / "runtime" / "schedule.json"
    )
    assert schedule_preview.resolve_output_path(str(tmp_path / "absolute.json")) == (
        tmp_path / "absolute.json"
    )


def test_generated_schedule_is_compatible_with_scheduler(tmp_path):
    output = tmp_path / "schedule.json"
    write_schedule(
        output=output,
        start_date="2026-07-18",
        num_days=2,
        times=["09:00"],
        replicates=2,
        replicate_interval_seconds=10,
    )

    jobs = expand_schedule(
        load_schedule(output),
        ZoneInfo("Europe/Amsterdam"),
    )

    assert [job.strftime("%Y-%m-%d %H:%M:%S") for job in jobs] == [
        "2026-07-18 09:00:00",
        "2026-07-18 09:00:10",
        "2026-07-19 09:00:00",
        "2026-07-19 09:00:10",
    ]
