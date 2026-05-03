from pathlib import Path

from web_server_test_support import load_web_module


def test_web_readme_page_uses_curated_help_instead_of_repository_readme(tmp_path):
    module = load_web_module()
    (tmp_path / "README.md").write_text(
        "# Local README\n\n"
        "Intro with <script>alert(1)</script>.\n\n"
        "```sh\n"
        "echo <safe>\n"
        "```\n",
        encoding="utf-8",
    )
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"), repo_dir=tmp_path)

    body = module.render_readme_page(settings)

    assert '<a class="brand" href="/" aria-label="Query Doctor home">' in body
    assert '<a class="nav-link" href="/">Recent scan</a>' in body
    assert '<a class="nav-link" href="/query">Query ID</a>' in body
    assert '<a class="nav-link nav-link--active" href="/help">Справка</a>' in body
    assert "<h1>README.md</h1>" not in body
    assert "<h1>Local README</h1>" not in body
    assert "Быстрый старт" in body
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" not in body
    assert "echo &lt;safe&gt;" not in body


def test_web_readme_page_handles_missing_readme(tmp_path):
    module = load_web_module()

    body = module.render_readme_page(
        module.WebSettings(config=Path(".query-doctor-cm.local.json"), repo_dir=tmp_path)
    )

    assert "Быстрый старт" in body
    assert "README.md was not found in the repository root." not in body


def test_web_readme_route_serves_curated_help_without_running_analysis(tmp_path):
    module = load_web_module()
    (tmp_path / "README.md").write_text("# Route README\n", encoding="utf-8")
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"), repo_dir=tmp_path)
    handler = module.make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    def write_html(status, body):
        captured["status"] = status
        captured["body"] = body

    request.path = "/readme"
    request.write_html = write_html

    request.do_GET()

    assert captured["status"] == 200
    assert "Быстрый старт" in captured["body"]
    assert "<h1>Route README</h1>" not in captured["body"]
