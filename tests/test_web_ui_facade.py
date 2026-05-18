from query_doctor.web.ui import facade


def test_package_web_ui_facade_exports_expected_helpers():
    assert callable(facade.render_page)
    assert callable(facade.render_batch_card)
    assert callable(facade.render_batch_case_detail_view_page)
    assert callable(facade.render_report_markdown_html)
    assert callable(facade.render_static_stylesheet_link)
    assert callable(facade.render_script_link)
    assert "render_page" in facade.__all__
    assert "render_batch_card" in facade.__all__
    assert "render_batch_case_detail_view_page" in facade.__all__
    assert "render_static_stylesheet_link" in facade.__all__
    assert "render_script_link" in facade.__all__
