from query_doctor.web.ui import facade


def test_package_web_ui_facade_exports_expected_helpers():
    assert callable(facade.render_page)
    assert callable(facade.render_batch_card)
    assert callable(facade.render_report_markdown_html)
    assert "render_page" in facade.__all__
    assert "render_batch_card" in facade.__all__
