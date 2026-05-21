from pathlib import Path

from web_server_test_support import load_web_module


def test_package_running_page_renderer_is_available():
    from query_doctor.web.ui import running

    assert callable(running.render_running_queries_page)
    assert hasattr(running, "render_running_queries_run_panel")


def test_web_running_page_renders_without_scan_window_fields_and_with_compact_help():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_running_queries_page(settings)

    assert "Scan date" not in body
    assert "Scan Hour" not in body
    assert 'name="cm_timeseries_top_limit"' not in body
    assert "Scan currently running Impala queries from the selected source." not in body
    assert "Live scan" in body
    assert "Live snapshot:" not in body
    assert "current running-query snapshot" in body
    assert "No date or hour window is used." in body
    assert "Profiles can be incomplete while queries execute" in body
    assert "Query Doctor may show fewer deterministic findings than after completion" in body
    assert "No LLM report or optimizer draft runs automatically" in body
    assert "Minimum duration (sec)" in body
    assert '<summary aria-label="Minimum duration (sec) help">i</summary>' in body
    assert "Username" not in body
    assert "Resource pool" not in body
    assert "Metadata parallelism" not in body
    assert "Advanced settings" not in body


def test_web_running_page_places_configured_source_before_live_scan():
    module = load_web_module()
    from query_doctor.web.models import WebClusterConfig

    settings = module.WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        clusters=(
            WebClusterConfig(key="prod", label="Production"),
            WebClusterConfig(key="stage", label="Staging"),
        ),
        active_cluster_key="stage",
    )

    body = module.render_running_queries_page(settings)

    assert '<label for="running_cluster_key">Source cluster</label>' in body
    assert '<select class="input" id="running_cluster_key" name="cluster_key">' in body
    assert '<option value="stage" selected>Staging</option>' in body
    assert body.index('<label for="running_cluster_key">Source cluster</label>') < body.index(
        "Live scan"
    )


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
    assert "Scan currently running Impala queries from the selected source." not in captured["body"]
    assert "current running-query snapshot" in captured["body"]
    assert "No date or hour window is used." in captured["body"]
    assert "Live snapshot:" not in captured["body"]
    assert "Profiles can be incomplete while queries execute" in captured["body"]
    assert "current running query summaries" not in captured["body"]
