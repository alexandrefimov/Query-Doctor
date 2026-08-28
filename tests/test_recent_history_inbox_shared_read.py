from __future__ import annotations

from query_doctor.web import recent_history_inbox


class _Settings:
    public_demo = False
    config = "/etc/query-doctor/query-doctor-config.json"


def _counting_loader(counter: dict[str, int]):
    def loader(settings: object) -> dict[str, object]:
        counter["calls"] += 1
        return {"rows": []}

    return loader


def test_a_render_reads_the_retained_history_once(monkeypatch):
    counter = {"calls": 0}
    monkeypatch.setattr(
        recent_history_inbox, "load_recent_history_inbox_summary", _counting_loader(counter)
    )
    settings = _Settings()

    with recent_history_inbox.shared_recent_history_inbox_summary():
        first = recent_history_inbox.recent_history_inbox_summary_from_settings(settings)
        second = recent_history_inbox.recent_history_inbox_summary_from_settings(settings)
        third = recent_history_inbox.recent_history_inbox_summary_from_settings(settings)

    # Three parts of one page ask for this; loading it three times is what made
    # the page slow.
    assert counter["calls"] == 1
    assert first is second is third


def test_the_memo_does_not_outlive_one_render(monkeypatch):
    counter = {"calls": 0}
    monkeypatch.setattr(
        recent_history_inbox, "load_recent_history_inbox_summary", _counting_loader(counter)
    )
    settings = _Settings()

    with recent_history_inbox.shared_recent_history_inbox_summary():
        recent_history_inbox.recent_history_inbox_summary_from_settings(settings)
    with recent_history_inbox.shared_recent_history_inbox_summary():
        recent_history_inbox.recent_history_inbox_summary_from_settings(settings)

    assert counter["calls"] == 2


def test_reading_outside_a_render_still_loads_every_time(monkeypatch):
    counter = {"calls": 0}
    monkeypatch.setattr(
        recent_history_inbox, "load_recent_history_inbox_summary", _counting_loader(counter)
    )
    settings = _Settings()

    recent_history_inbox.recent_history_inbox_summary_from_settings(settings)
    recent_history_inbox.recent_history_inbox_summary_from_settings(settings)

    assert counter["calls"] == 2
