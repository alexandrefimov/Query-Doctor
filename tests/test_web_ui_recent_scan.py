from query_doctor.web.ui import recent_scan, recent_scan_results


def test_recent_scan_facade_renderers_are_available():
    assert callable(recent_scan.render_batch_card)
    assert callable(recent_scan.render_batch_run_panel)
    assert hasattr(recent_scan, "render_batch_case_detail")


def test_recent_scan_results_helpers_are_available():
    assert callable(recent_scan_results.render_batch_summary)
    assert recent_scan_results.normalize_query_group("stats") == "stats"
    assert recent_scan_results.normalize_query_group("missing") == recent_scan_results.DEFAULT_QUERY_GROUP


def test_optimizer_next_action_labels_are_action_oriented():
    assert recent_scan_results.optimizer_next_action_view("trusted_draft")[0] == "Open draft"
    assert recent_scan_results.optimizer_next_action_view("trusted_recommendations")[0] == "Open guidance"
    assert recent_scan_results.optimizer_next_action_view("trusted_no_rewrite")[0] == "Open outcome"
    assert recent_scan_results.optimizer_next_action_view("partial_untrusted")[0] == "Validate manually"
    assert recent_scan_results.optimizer_next_action_view("not_run")[0] == "Generate draft"
