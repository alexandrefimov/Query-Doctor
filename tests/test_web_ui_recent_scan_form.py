from query_doctor.web.ui import recent_scan_form


def test_recent_scan_form_defaults_are_available():
    assert recent_scan_form.WEB_RECENT_SCAN_DEFAULTS["parallelism"] == "50"
    assert hasattr(recent_scan_form, "render_batch_run_panel")
