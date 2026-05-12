from pathlib import Path

from web_server_test_support import load_web_module


def test_package_running_page_renderer_is_available():
    from query_doctor.web.ui import running

    assert callable(running.render_running_queries_page)
    assert hasattr(running, "render_running_queries_run_panel")


def test_web_running_page_renders_without_scan_window_fields_and_with_bounds_note():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_running_queries_page(settings)

    assert "Scan date" not in body
    assert "Scan Hour" not in body
    assert (
        "Runtime context is collected automatically when the selected source supports it." in body
    )
    assert 'name="cm_timeseries_top_limit"' not in body
    assert "Live snapshot:" in body
    assert "no date/hour window is used" in body
    assert "profiles can be incomplete while queries execute" in body
    assert "may show fewer deterministic findings than after completion" in body
    assert "No LLM report or optimizer draft runs automatically" in body
    assert "Minimum duration (sec)" in body
    assert "Username" in body
    assert "Resource pool" in body
    assert "Metadata parallelism" in body


def test_web_running_route_renders_page():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    def write_html(status: int, body: str) -> None:
        captured["status"] = status
        captured["body"] = body

    request.path = "/running"
    request.write_html = write_html

    request.do_GET()

    assert captured["status"] == 200
    assert "Running Queries" in captured["body"]
    assert "current running query summaries" in captured["body"]
    assert (
        "Runtime context is collected automatically when the selected source supports it."
        in captured["body"]
    )
    assert "Live snapshot:" in captured["body"]
    assert "profiles can be incomplete while queries execute" in captured["body"]
