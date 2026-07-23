from datetime import date

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


def test_react_router_owns_the_main_navigation_in_workflow_order():
    source = (FRONTEND / "components.jsx").read_text()
    navigation = source[source.index("function Navigation") :]

    scheduler = navigation.index('to="/scheduler"')
    schedule = navigation.index('to="/schedule"')
    camera = navigation.index('to="/camera"')

    assert scheduler < schedule < camera
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
