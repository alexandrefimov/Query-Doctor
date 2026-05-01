from pathlib import Path

from web_server_test_support import load_web_module


def test_web_readme_page_renders_repository_readme_safely(tmp_path):
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
    assert '<a class="nav-link" href="/">Run</a>' in body
    assert '<a class="nav-link nav-link--active" href="/readme">README</a>' in body
    assert "<h1>README.md</h1>" in body
    assert "<h1>Local README</h1>" in body
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "echo &lt;safe&gt;" in body


def test_web_readme_page_handles_missing_readme(tmp_path):
    module = load_web_module()

    body = module.render_readme_page(
        module.WebSettings(config=Path(".query-doctor-cm.local.json"), repo_dir=tmp_path)
    )

    assert "README.md не найден в корне репозитория." in body


def test_web_readme_route_serves_readme_without_running_analysis(tmp_path):
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
    assert "<h1>Route README</h1>" in captured["body"]
