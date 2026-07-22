from datetime import date

from starlette.requests import Request

from gui.app import app
from gui.config import APP_DIR, templates
from gui.routes.schedule import index
from gui.routes import scheduler as scheduler_routes
from gui.services.schedule_preview import ScheduleFormData, persist_schedule_draft


def template_source(name):
    source, _, _ = templates.env.loader.get_source(templates.env, name)
    return source


def request_for(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("test", 1),
            "server": ("testserver", 80),
            "app": app,
        }
    )


def draft_form() -> ScheduleFormData:
    return ScheduleFormData(
        mode="every",
        start_date=date.today().isoformat(),
        num_days=2,
        replicates=1,
        replicate_interval_seconds=0,
        every_start="09:00",
        every_end="10:00",
        every_step_minutes=30,
    )


def test_main_navigation_contains_only_implemented_pages_in_workflow_order():
    source = template_source("base.html")
    source = source[source.index('<nav class="tabs"') : source.index("</nav>")]

    camera = source.index('href="/camera"')
    schedule = source.index('href="/schedule"')
    scheduler = source.index('href="/scheduler"')

    assert scheduler < camera < schedule
    assert "tab disabled" not in source
    assert "Acquisition" not in source
    assert "Canopy analysis" not in source
    assert "Growth plots" not in source


def test_camera_preview_leads_directly_to_schedule_setup():
    source = template_source("camera.html")

    assert "Camera preview is optional during development" in source
    assert "does not verify the Raspberry Pi capture camera" in source
    assert 'href="/schedule"' in source
    assert "Continue to schedule setup" in source


def test_root_opens_scheduler_status():
    assert str(app.url_path_for("index")) == "/"
    response = index()
    assert response.status_code == 303
    assert response.headers["location"] == "/scheduler"


def test_scheduler_page_reports_ready_invalid_and_missing_drafts(
    tmp_path, monkeypatch
):
    draft_path = tmp_path / "schedule-draft.json"
    monkeypatch.setattr(scheduler_routes, "SCHEDULE_DRAFT_PATH", draft_path)

    assert scheduler_routes.schedule_draft_state() == "none"

    draft_path.write_text("")
    assert scheduler_routes.schedule_draft_state() == "invalid"

    persist_schedule_draft(draft_form(), draft_path)
    assert scheduler_routes.schedule_draft_state() == "ready"


def test_scheduler_page_has_one_context_sensitive_next_action():
    source = template_source("scheduler.html")
    script = (APP_DIR / "static" / "scheduler_status.js").read_text()

    assert source.count('id="schedule-action"') == 1
    assert source.count('id="schedule-empty-link"') == 1
    assert 'id="schedule-draft-state"' in source
    assert 'scheduleDraftState === "ready"' in script
    assert 'scheduleDraftState === "invalid"' in script
    assert 'schedule.lifecycle === "finished"' in script
    assert '"Review draft", "/schedule/review"' in script
    assert '"Create next schedule", "/schedule"' in script
    assert script.index('scheduleDraftState === "ready"') < script.index(
        'schedule.lifecycle === "finished"'
    )
