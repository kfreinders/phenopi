from datetime import date

import pytest
from fastapi import HTTPException

from gui.app import app
from gui.routes import scheduler as scheduler_routes
from gui.services.schedule_drafts import persist_schedule_draft
from gui.services.schedule_form import ScheduleFormData


FRONTEND = app_dir = __import__("gui.config", fromlist=["APP_DIR"]).APP_DIR / "frontend" / "src"


def draft_form() -> ScheduleFormData:
    return ScheduleFormData(
        mode="every",
        experiment_name="Navigation test",
        start_date=date.today().isoformat(),
        num_days=2,
        replicates=1,
        replicate_interval_seconds=0,
        every_start="09:00",
        every_end="10:00",
        every_step_minutes=30,
    )


def test_main_navigation_keeps_the_builder_as_a_contextual_workflow():
    source = (FRONTEND / "components.jsx").read_text()
    navigation = source[source.index("function Navigation") :]

    assert navigation.index('to="/scheduler"') < navigation.index('to="/camera"')
    assert 'to="/schedule"' not in navigation
    assert "React Router" not in navigation


def test_camera_preview_leads_directly_to_schedule_setup():
    source = (FRONTEND / "pages" / "CameraPage.jsx").read_text()

    assert "Camera preview is optional during development" in source
    assert "does not verify the Raspberry Pi capture camera" in source
    assert 'to="/schedule"' in source
    assert "Continue to schedule setup" in source


def test_spa_fallback_and_all_user_routes_are_registered_in_react():
    assert str(app.url_path_for("react_app", path="scheduler")) == "/scheduler"
    source = (FRONTEND / "App.jsx").read_text()
    for route in (
        'path="scheduler"',
        'path="schedule"',
        'path="schedule/edit"',
        'path="schedule/review"',
        'path="schedule/activation"',
        'path="camera"',
    ):
        assert route in source


def test_activation_page_rejects_a_malformed_schedule_hash():
    source = (FRONTEND / "pages" / "ActivationPage.jsx").read_text()

    assert "/^[0-9a-f]{64}$/" in source
    assert "Invalid activation link" in source


def test_scheduler_api_reports_ready_invalid_and_missing_drafts(
    tmp_path, monkeypatch
):
    draft_path = tmp_path / "schedule-draft.json"
    monkeypatch.setattr(scheduler_routes, "SCHEDULE_DRAFT_PATH", draft_path)

    assert scheduler_routes.schedule_draft_state() == "none"
    draft_path.write_text("")
    assert scheduler_routes.schedule_draft_state() == "invalid"
    persist_schedule_draft(draft_form(), draft_path)
    assert scheduler_routes.scheduler_status_api()["draft_state"] == "ready"


def test_scheduler_page_has_context_sensitive_next_actions():
    source = (FRONTEND / "pages" / "SchedulerPage.jsx").read_text()

    assert 'draftState === "ready"' in source
    assert 'draftState === "invalid"' in source
    assert 'schedule?.lifecycle !== "finished"' in source
    assert "Review draft" in source
    assert "Create next schedule" in source
    assert "Experiment finished with capture issues" in source
    assert "Replace schedule…" in source


def test_cancel_api_requires_a_healthy_matching_active_schedule(
    tmp_path, monkeypatch
):
    command_path = tmp_path / "scheduler-command.json"
    schedule_hash = "c" * 64
    monkeypatch.setattr(scheduler_routes, "SCHEDULER_COMMAND_PATH", command_path)
    monkeypatch.setattr(
        scheduler_routes,
        "read_scheduler_status",
        lambda path: {
            "status": "healthy",
            "schedule": {"hash": schedule_hash, "lifecycle": "active"},
        },
    )

    response = scheduler_routes.cancel_scheduled_experiment(
        scheduler_routes.CancellationRequest(schedule_hash=schedule_hash)
    )

    assert response["accepted"] is True
    assert command_path.exists()
    assert scheduler_routes._cancellation_pending(schedule_hash) is True

    with pytest.raises(HTTPException) as mismatch:
        scheduler_routes.cancel_scheduled_experiment(
            scheduler_routes.CancellationRequest(schedule_hash="d" * 64)
        )
    assert mismatch.value.status_code == 409


def test_cancel_api_accepts_an_upcoming_schedule(tmp_path, monkeypatch):
    command_path = tmp_path / "scheduler-command.json"
    schedule_hash = "e" * 64
    monkeypatch.setattr(scheduler_routes, "SCHEDULER_COMMAND_PATH", command_path)
    monkeypatch.setattr(
        scheduler_routes,
        "read_scheduler_status",
        lambda path: {
            "status": "healthy",
            "schedule": {"hash": schedule_hash, "lifecycle": "upcoming"},
        },
    )

    response = scheduler_routes.cancel_scheduled_experiment(
        scheduler_routes.CancellationRequest(schedule_hash=schedule_hash)
    )

    assert response["accepted"] is True
    assert scheduler_routes._cancellation_pending(schedule_hash) is True
