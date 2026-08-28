from __future__ import annotations

from query_doctor.recent.materialized_case_index import materialized_case_entries
from query_doctor.web.presenters.recent_scan import present_recent_scan_summary
from query_doctor.web.presenters.recent_scan_summary import (
    recent_scan_empty_message,
    recent_scan_scope_parts,
    recent_scan_warning_messages,
)


def _summary_with_cases(count: int) -> dict[str, object]:
    return {
        "recent_history": {
            "materialized_cases": [
                {
                    "query_id": f"aa4a1b340c9f8e2{index:d}:1a2b3c4d00000000",
                    "duration_sec": 12.5,
                    "status": "finished",
                    "analysis_cache_payload": {"score": 0, "score_severity": "clean"},
                }
                for index in range(count)
            ]
        },
        "warnings": ["one retained warning"],
    }


def test_scope_parts_and_warnings_do_not_need_presented_rows():
    summary = _summary_with_cases(4)

    view = present_recent_scan_summary(summary)

    # Three call sites used to build every presented row to read one of these.
    assert tuple(view.scope_parts) == tuple(recent_scan_scope_parts(summary))
    assert tuple(view.warning_messages) == tuple(recent_scan_warning_messages(summary))


def test_empty_message_needs_only_how_many_cases_there_are():
    for count in (0, 1, 4):
        summary = _summary_with_cases(count)

        view = present_recent_scan_summary(summary)
        case_count = len(materialized_case_entries(summary))

        assert case_count == len(view.rows)
        assert view.empty_message == recent_scan_empty_message(summary, case_count=case_count)
