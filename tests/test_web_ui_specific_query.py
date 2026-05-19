from query_doctor.web.ui import specific_query


def test_specific_query_renderers_are_available():
    assert callable(specific_query.render_specific_query_results)
    assert callable(specific_query.render_specific_query_detail_view)
    assert specific_query.specific_query_report_href("abc:def") == "/query/details/abc%3Adef/report"
    assert (
        specific_query.specific_query_actions_href("abc:def", llm_enabled=False)
        == "/query/details/abc%3Adef/case-actions"
    )
    assert (
        specific_query.specific_query_llm_actions_href("abc:def")
        == "/query/details/abc%3Adef/llm-actions"
    )
