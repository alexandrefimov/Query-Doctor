import json

from query_doctor.web.jobs import WebJobStore, render_job_status_json


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_web_job_store_prunes_expired_terminal_jobs_but_keeps_running_jobs():
    clock = FakeClock()
    store = WebJobStore(terminal_job_ttl_sec=10, clock=clock)
    completed = store.create_batch({"scan_target": "finished"})
    running = store.create_running_batch({"scan_target": "running"})

    store.complete_html(completed.job_id, "safe result")
    clock.advance(11)

    assert store.get(completed.job_id) is None
    assert store.get(running.job_id) is not None


def test_web_job_store_prunes_oldest_terminal_jobs_by_count():
    clock = FakeClock()
    store = WebJobStore(max_terminal_jobs=2, clock=clock)
    first = store.create_batch({"scan_target": "finished"})
    store.complete_html(first.job_id, "first")
    clock.advance(1)
    second = store.create_batch_report("case-001")
    store.complete_html(second.job_id, "second")
    clock.advance(1)
    third = store.create_query_report("abc:def")
    store.complete_html(third.job_id, "third")

    assert store.get(first.job_id) is None
    assert store.get(second.job_id) is not None
    assert store.get(third.job_id) is not None


def test_web_job_store_terminal_timestamps_stay_internal():
    store = WebJobStore()
    job = store.create_batch({"scan_target": "finished"})
    store.complete_html(job.job_id, "safe result")
    snapshot = store.get(job.job_id)

    assert snapshot is not None
    assert not hasattr(snapshot, "created_at")
    assert not hasattr(snapshot, "updated_at")
    payload = json.loads(render_job_status_json(snapshot))
    assert "created_at" not in payload
    assert "updated_at" not in payload


def test_web_job_store_updates_terminal_ttl_when_job_finishes():
    clock = FakeClock()
    store = WebJobStore(terminal_job_ttl_sec=10, clock=clock)
    job = store.create_batch({"scan_target": "finished"})
    clock.advance(9)
    store.complete_html(job.job_id, "safe result")
    clock.advance(9)

    assert store.get(job.job_id) is not None

    clock.advance(2)

    assert store.get(job.job_id) is None
