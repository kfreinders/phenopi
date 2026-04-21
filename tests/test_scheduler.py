from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scripts.scheduling.scheduler import process_jobs


def test_process_jobs_runs_due_job_and_marks_complete():
    tz = ZoneInfo("Europe/Amsterdam")
    job_time = datetime(2026, 4, 21, 9, 0, tzinfo=tz)
    jobs = [job_time]
    completed = set()
    now = datetime(2026, 4, 21, 9, 5, tzinfo=tz)

    calls = []

    def fake_run_capture():
        calls.append("called")
        return True

    changed = process_jobs(
        jobs=jobs,
        completed=completed,
        now=now,
        max_lateness=timedelta(minutes=10),
        run_capture_fn=fake_run_capture,
    )

    assert changed is True
    assert completed == {job_time.isoformat()}
    assert calls == ["called"]


def test_process_jobs_skips_completed_job():
    tz = ZoneInfo("Europe/Amsterdam")
    job_time = datetime(2026, 4, 21, 9, 0, tzinfo=tz)
    jobs = [job_time]
    completed = {job_time.isoformat()}
    now = datetime(2026, 4, 21, 9, 5, tzinfo=tz)

    calls = []

    def fake_run_capture():
        calls.append("called")
        return True

    changed = process_jobs(
        jobs=jobs,
        completed=completed,
        now=now,
        max_lateness=timedelta(minutes=10),
        run_capture_fn=fake_run_capture,
    )

    assert changed is False
    assert calls == []


def test_process_jobs_skips_job_if_too_early():
    tz = ZoneInfo("Europe/Amsterdam")
    job_time = datetime(2026, 4, 21, 9, 0, tzinfo=tz)
    jobs = [job_time]
    completed = set()
    now = datetime(2026, 4, 21, 8, 59, tzinfo=tz)

    calls = []

    def fake_run_capture():
        calls.append("called")
        return True

    changed = process_jobs(
        jobs=jobs,
        completed=completed,
        now=now,
        max_lateness=timedelta(minutes=10),
        run_capture_fn=fake_run_capture,
    )

    assert changed is False
    assert calls == []


def test_process_jobs_skips_job_if_too_late():
    tz = ZoneInfo("Europe/Amsterdam")
    job_time = datetime(2026, 4, 21, 9, 0, tzinfo=tz)
    jobs = [job_time]
    completed = set()
    now = datetime(2026, 4, 21, 9, 11, tzinfo=tz)

    calls = []

    def fake_run_capture():
        calls.append("called")
        return True

    changed = process_jobs(
        jobs=jobs,
        completed=completed,
        now=now,
        max_lateness=timedelta(minutes=10),
        run_capture_fn=fake_run_capture,
    )

    assert changed is True
    assert calls == []


def test_process_jobs_failed_capture_does_not_mark_complete():
    tz = ZoneInfo("Europe/Amsterdam")
    job_time = datetime(2026, 4, 21, 9, 0, tzinfo=tz)
    jobs = [job_time]
    completed = set()
    now = datetime(2026, 4, 21, 9, 2, tzinfo=tz)

    def fake_run_capture():
        return False

    changed = process_jobs(
        jobs=jobs,
        completed=completed,
        now=now,
        max_lateness=timedelta(minutes=10),
        run_capture_fn=fake_run_capture,
    )

    assert changed is False
    assert completed == set()
