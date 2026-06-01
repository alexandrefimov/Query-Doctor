from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "web_static_smoke.py"
APP_JS_PATH = Path(__file__).resolve().parents[1] / "query_doctor" / "web" / "static" / "app.js"
SPEC = importlib.util.spec_from_file_location("web_static_smoke", SCRIPT_PATH)
assert SPEC is not None
web_static_smoke = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = web_static_smoke
SPEC.loader.exec_module(web_static_smoke)


def response(
    body: str,
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
    csp: str | None = None,
) -> web_static_smoke.HttpResponse:
    encoded = body.encode("utf-8")
    headers = {
        "content-type": content_type,
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "content-length": str(len(encoded)),
        "content-security-policy": csp
        or (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        ),
    }
    return web_static_smoke.HttpResponse(status=status, headers=headers, body=encoded)


def test_check_home_accepts_external_static_assets():
    failures: list[str] = []

    web_static_smoke.check_home(
        response(
            '<html><head><script src="/static/theme-bootstrap.js"></script>'
            '<link rel="stylesheet" href="/static/app.css">'
            '<script src="/static/app.js"></script></head><body>Diagnose</body></html>'
        ),
        failures,
    )

    assert failures == []


def test_check_home_requires_expected_text():
    failures: list[str] = []

    web_static_smoke.check_home(
        response(
            '<html><head><script src="/static/theme-bootstrap.js"></script>'
            '<link rel="stylesheet" href="/static/app.css">'
            '<script src="/static/app.js"></script></head><body>Diagnose</body></html>'
        ),
        failures,
        expected_text=("demo-optimizer-0001",),
    )

    assert failures == ["GET /: missing expected text 'demo-optimizer-0001'"]


def test_check_home_rejects_inline_style_and_unsafe_inline_csp():
    failures: list[str] = []

    web_static_smoke.check_home(
        response(
            "<html><head><style>color-scheme:light</style></head></html>",
            csp=(
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; base-uri 'none'; "
                "form-action 'self'; frame-ancestors 'none'"
            ),
        ),
        failures,
    )

    assert any("unsafe-inline" in failure for failure in failures)
    assert any("unexpected inline <style>" in failure for failure in failures)
    assert any("product CSS leaked inline" in failure for failure in failures)


def test_check_static_asset_requires_type_marker_headers_and_length():
    failures: list[str] = []

    web_static_smoke.check_static_asset(
        response(
            "body { color-scheme:light }",
            content_type="text/css; charset=utf-8",
        ),
        "/static/app.css",
        "text/css; charset=utf-8",
        "color-scheme:light",
        failures,
    )

    assert failures == []


def test_check_static_rejection_blocks_source_leaks():
    failures: list[str] = []

    web_static_smoke.check_static_rejection(
        response("HTTP handler factory", status=404),
        "/static/../app.py",
        failures,
    )

    assert failures == ["GET /static/../app.py: response leaked 'HTTP handler factory'"]


def test_parse_expected_path_text_requires_path_separator_and_text():
    assert web_static_smoke.parse_expected_path_text(["/?query_group=stats::demo-stats-0002"]) == (
        ("/?query_group=stats", "demo-stats-0002"),
    )

    for value in ("missing-separator", "stats::demo", "/stats::"):
        try:
            web_static_smoke.parse_expected_path_text([value])
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {value!r}")


def test_normalize_base_url_rejects_credentials():
    try:
        web_static_smoke.normalize_base_url("http://user:" + "pass@127.0.0.1:8766")
    except ValueError as exc:
        assert "credentials" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_app_js_restores_run_buttons_for_all_scan_job_kinds():
    script = APP_JS_PATH.read_text(encoding="utf-8")

    assert "function restoreRunButtons(kind)" in script
    assert "restoreRunButtons(data.kind)" in script
    assert "kind === 'batch'" in script
    assert "kind === 'running'" in script
    assert "kind === 'query'" in script
    assert '#batch-form button[type="submit"]' in script
    assert '#running-form button[type="submit"]' in script
    assert '#analyze-form button[type="submit"]' in script
