from query_doctor.web.presenters.recent_scan import (
    present_recent_scan_case_detail,
    present_recent_scan_metadata,
)
from query_doctor.web.ui.metadata_details import render_metadata_facts_body
from query_doctor.web.ui.recent_scan_details import render_recent_scan_case_detail_view


FORBIDDEN_DISPLAY_FRAGMENTS = (
    "/Users/",
    "/tmp/",
    "case_dir",
    "BEGIN PROFILE",
    "Query Timeline",
    "original_query.sql",
    "profile_digest.md",
    "analysis_facts.md",
    "stdout",
    "stderr",
)


def assert_no_forbidden_fragments(value: object) -> None:
    text = repr(value)
    for fragment in FORBIDDEN_DISPLAY_FRAGMENTS:
        assert fragment not in text


def test_recent_scan_metadata_view_renders_collectable_table_count_safely():
    view = present_recent_scan_metadata(
        {
            "metadata_status": "not_requested",
            "referenced_table_count": 0,
            "collectable_metadata_table_count": 1,
            "collected_metadata_table_count": 0,
            "too_large_count": 0,
        },
        None,
    )
    detail_view = present_recent_scan_case_detail(
        "case-001",
        {
            "query_id": "abc",
            "score": 0,
            "collection_status": "ok",
            "analysis_status": "ok",
            "metadata_status": "not_requested",
            "referenced_table_count": 0,
            "collectable_metadata_table_count": 1,
            "collected_metadata_table_count": 0,
            "too_large_count": 0,
        },
    )

    summary = dict(view.summary_items)
    html = render_metadata_facts_body(view)
    detail_html = render_recent_scan_case_detail_view(detail_view)

    assert view.unavailable is False
    assert "Safe aggregate metadata facts" in view.fallback_note
    assert summary["collectable metadata tables"] == 1
    assert "collectable metadata tables" in html
    assert "collectable metadata tables" in detail_html
    assert_no_forbidden_fragments((summary, html, detail_html))
