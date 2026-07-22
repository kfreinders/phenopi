import json
from datetime import date, datetime, timedelta, timezone

from starlette.requests import Request

from gui.app import app
from gui.config import APP_DIR
from gui.routes import schedule as schedule_routes
from gui.services.schedule_preview import ScheduleFormData, persist_schedule_draft


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


def schedule_form_data() -> ScheduleFormData:
    return ScheduleFormData(
        mode="every",
        experiment_name="Seedling drought response",
        start_date=date.today().isoformat(),
        num_days=2,
        replicates=2,
        replicate_interval_seconds=10,
        every_start="09:00",
        every_end="10:00",
        every_step_minutes=30,
    )


def write_heartbeat(
    path,
    *,
    age_seconds=0,
    state="waiting_for_schedule",
    schedule=None,
    storage=None,
):
    timestamp = datetime.now(timezone.utc).timestamp() - age_seconds
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "timestamp": datetime.fromtimestamp(
                    timestamp, timezone.utc
                ).isoformat(),
                "state": state,
                "message": "test scheduler state",
                "schedule": schedule,
                "last_capture": None,
                "storage": storage,
            }
        )
    )


def configure_paths(monkeypatch, tmp_path):
    draft_path = tmp_path / "schedule-draft.json"
    schedule_path = tmp_path / "schedule.json"
    heartbeat_path = tmp_path / "scheduler-heartbeat.json"
    monkeypatch.setattr(schedule_routes, "SCHEDULE_DRAFT_PATH", draft_path)
    monkeypatch.setattr(schedule_routes, "DEFAULT_SCHEDULE_PATH", schedule_path)
    monkeypatch.setattr(
        schedule_routes, "SCHEDULER_HEARTBEAT_PATH", heartbeat_path
    )
    return draft_path, schedule_path, heartbeat_path


def test_configure_page_makes_workflow_and_next_action_explicit(
    tmp_path, monkeypatch
):
    configure_paths(monkeypatch, tmp_path)

    html = schedule_routes.schedule_form(request_for("/schedule")).body.decode()

    assert "Configure" in html
    assert "Review" in html
    assert "Activate" in html
    assert "Confirmed" in html
    assert "Continue to review" in html
    assert 'name="output"' not in html
    assert 'name="overwrite"' not in html
    assert 'name="num_days" min="1" max="3650"' in html
    assert 'name="replicates" min="1" max="100"' in html
    assert f'min="{date.today().isoformat()}"' in html


def test_preview_persists_draft_and_schedule_page_resumes_review(
    tmp_path, monkeypatch
):
    draft_path, _, heartbeat_path = configure_paths(monkeypatch, tmp_path)
    write_heartbeat(heartbeat_path)

    response = schedule_routes.preview_schedule(
        request_for("/schedule/preview"), schedule_form_data()
    )
    resume = schedule_routes.schedule_form(request_for("/schedule"))
    review = schedule_routes.review_schedule(
        request_for("/schedule/review")
    ).body.decode()

    assert response.status_code == 303
    assert response.headers["location"] == "/schedule/review"
    assert draft_path.exists()
    assert resume.headers["location"] == "/schedule/review"
    assert "Review before activation" in review
    assert "Nothing changes in the scheduler until you activate" in review


def test_activation_is_blocked_while_scheduler_is_stale(
    tmp_path, monkeypatch
):
    draft_path, schedule_path, heartbeat_path = configure_paths(
        monkeypatch, tmp_path
    )
    draft = persist_schedule_draft(schedule_form_data(), draft_path)
    write_heartbeat(heartbeat_path, age_seconds=31)

    response = schedule_routes.activate_schedule(
        request_for("/schedule/activate"), draft.schedule_hash
    )
    html = response.body.decode()

    assert "Activation is blocked" in html
    assert draft_path.exists()
    assert not schedule_path.exists()


def test_activation_is_blocked_when_protected_estimate_exceeds_storage(
    tmp_path, monkeypatch
):
    draft_path, schedule_path, heartbeat_path = configure_paths(
        monkeypatch, tmp_path
    )
    draft = persist_schedule_draft(schedule_form_data(), draft_path)
    write_heartbeat(
        heartbeat_path,
        storage={"free_bytes": 100_000_000, "used_percent": 50.0},
    )

    review = schedule_routes.review_schedule(
        request_for("/schedule/review")
    ).body.decode()
    activation = schedule_routes.activate_schedule(
        request_for("/schedule/activate"), draft.schedule_hash
    )

    assert "Not enough storage for this experiment" in review
    assert "182.4 MB" in review
    assert "100 MB" in review
    assert "Activation is blocked" in activation.body.decode()
    assert draft_path.exists()
    assert not schedule_path.exists()


def test_review_prominently_identifies_an_already_active_schedule(
    tmp_path, monkeypatch
):
    draft_path, _, heartbeat_path = configure_paths(monkeypatch, tmp_path)
    draft = persist_schedule_draft(schedule_form_data(), draft_path)
    write_heartbeat(
        heartbeat_path,
        state="running",
        schedule={
            "hash": draft.schedule_hash,
            "timezone": "Europe/Amsterdam",
            **draft.schedule,
        },
    )

    html = schedule_routes.review_schedule(
        request_for("/schedule/review")
    ).body.decode()

    assert "This schedule is already active" in html
    assert "No activation is needed" in html
    assert ">Already active</button>" in html


def test_review_does_not_compare_draft_with_a_finished_schedule(
    tmp_path, monkeypatch
):
    draft_path, _, heartbeat_path = configure_paths(monkeypatch, tmp_path)
    persist_schedule_draft(schedule_form_data(), draft_path)
    finished_snapshot = {
        "hash": "a" * 64,
        "timezone": "Europe/Amsterdam",
        "start_date": (date.today() - timedelta(days=4)).isoformat(),
        "num_days": 2,
        "times": ["08:00", "16:00"],
        "replicates": 3,
        "replicate_interval_seconds": 15,
    }
    write_heartbeat(
        heartbeat_path,
        state="waiting_for_schedule",
        schedule=finished_snapshot,
    )

    html = schedule_routes.review_schedule(
        request_for("/schedule/review")
    ).body.decode()

    assert "Review before activation" in html
    assert "Changes from active schedule" not in html
    assert 'class="comparison-card card"' not in html


def test_active_schedule_requires_confirmation_before_atomic_promotion(
    tmp_path, monkeypatch
):
    draft_path, schedule_path, heartbeat_path = configure_paths(
        monkeypatch, tmp_path
    )
    draft = persist_schedule_draft(schedule_form_data(), draft_path)
    active_snapshot = {
        "hash": "a" * 64,
        "timezone": "Europe/Amsterdam",
        "start_date": (date.today() - timedelta(days=1)).isoformat(),
        "num_days": 3,
        "times": ["00:00", "23:59"],
        "replicates": 1,
        "replicate_interval_seconds": 0,
    }
    write_heartbeat(
        heartbeat_path,
        state="running",
        schedule=active_snapshot,
    )

    warning = schedule_routes.activate_schedule(
        request_for("/schedule/activate"), draft.schedule_hash
    )
    activated = schedule_routes.activate_schedule(
        request_for("/schedule/activate"),
        draft.schedule_hash,
        confirm_active_replacement="on",
    )

    assert "Replace the schedule during an active experiment?" in warning.body.decode()
    assert warning.status_code == 200
    assert activated.status_code == 303
    assert activated.headers["location"].endswith(draft.schedule_hash)
    assert json.loads(schedule_path.read_text()) == draft.schedule
    assert not draft_path.exists()


def test_schedule_workflow_routes_are_registered():
    assert str(app.url_path_for("review_schedule")) == "/schedule/review"
    assert str(app.url_path_for("activate_schedule")) == "/schedule/activate"
    assert str(app.url_path_for("schedule_activation")) == (
        "/schedule/activation"
    )


def test_activation_page_rejects_invalid_hash():
    response = schedule_routes.schedule_activation(
        request_for("/schedule/activation"), "not-a-hash"
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/schedule"


def test_activation_page_waits_for_scheduler_hash(tmp_path, monkeypatch):
    _, _, heartbeat_path = configure_paths(monkeypatch, tmp_path)
    write_heartbeat(heartbeat_path)

    html = schedule_routes.schedule_activation(
        request_for("/schedule/activation"), "a" * 64
    ).body.decode()

    assert "Waiting for scheduler confirmation" in html
    assert "schedule_activation.js?v=" in html


def test_confirmed_activation_marks_every_workflow_step_complete(
    tmp_path, monkeypatch
):
    draft_path, _, heartbeat_path = configure_paths(monkeypatch, tmp_path)
    draft = persist_schedule_draft(schedule_form_data(), draft_path)
    write_heartbeat(
        heartbeat_path,
        state="running",
        schedule={
            "hash": draft.schedule_hash,
            "timezone": "Europe/Amsterdam",
            **draft.schedule,
        },
    )

    html = schedule_routes.schedule_activation(
        request_for("/schedule/activation"), draft.schedule_hash
    ).body.decode()

    assert html.count("workflow-step--complete") == 4
    assert "workflow-step--current" not in html


def test_activation_client_polls_until_confirmation_or_timeout():
    contents = (APP_DIR / "static" / "schedule_activation.js").read_text()

    assert 'fetch("/api/scheduler/status"' in contents
    assert "2000" in contents
    assert "90000" in contents
    assert "expectedScheduleHash" in contents
    assert 'workflow-step")[3].className = "workflow-step workflow-step--complete"' in contents
    assert 'window.location.assign("/scheduler")' in contents
    assert "seconds = 3" in contents


def test_confirmed_page_redirects_without_offering_another_schedule(
    tmp_path, monkeypatch
):
    draft_path, _, heartbeat_path = configure_paths(monkeypatch, tmp_path)
    draft = persist_schedule_draft(schedule_form_data(), draft_path)
    write_heartbeat(
        heartbeat_path,
        state="running",
        schedule={
            "hash": draft.schedule_hash,
            "timezone": "Europe/Amsterdam",
            **draft.schedule,
        },
    )

    html = schedule_routes.schedule_activation(
        request_for("/schedule/activation"), draft.schedule_hash
    ).body.decode()

    assert "Opening Scheduler Status" in html
    assert "Create another schedule" not in html
    assert "View scheduler status" not in html
