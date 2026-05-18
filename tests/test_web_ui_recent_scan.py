from query_doctor.web.ui import recent_scan, recent_scan_results


def test_recent_scan_facade_renderers_are_available():
    assert callable(recent_scan.render_batch_card)
    assert callable(recent_scan.render_batch_run_panel)
    assert hasattr(recent_scan, "render_recent_scan_case_detail_view")


def test_recent_scan_results_helpers_are_available():
    assert callable(recent_scan_results.render_batch_summary)
    assert recent_scan_results.normalize_query_group("stats") == "stats"
    assert (
        recent_scan_results.normalize_query_group("missing")
        == recent_scan_results.DEFAULT_QUERY_GROUP
    )
