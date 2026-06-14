import io
from pathlib import Path

import pytest

from query_doctor.web.audit import WebAuditEvent, render_web_audit_log_line
from query_doctor.web.app import (
    MAX_WEB_POST_BODY_BYTES,
    explicit_request_host_port,
    forwarded_header_host_values,
    forwarded_host_values,
    forwarded_port_values,
    make_handler,
    new_request_id,
    normalized_request_host,
    parse_post_content_length,
    read_bounded_post_form,
    request_host_allowed,
    request_origin_allowed,
    settings_for_request_headers,
)
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.routes import WebRouteResponse, route_get_request
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.viewer_identity import (
    VIEWER_IDENTITY_AUTHENTICATED,
    VIEWER_IDENTITY_UNAUTHENTICATED,
)


class UnreadableBody(io.BytesIO):
    def read(self, *args, **kwargs):
        raise AssertionError(
            "invalid Content-Length should be rejected before reading the request body"
        )


@pytest.mark.parametrize("value", ["not-an-int", "-1"])
def test_parse_post_content_length_rejects_invalid_values(value):
    with pytest.raises(WebError, match="Invalid POST content length"):
        parse_post_content_length(value)


def test_parse_post_content_length_defaults_missing_to_zero():
    assert parse_post_content_length(None) == 0
    assert parse_post_content_length("") == 0


def test_read_bounded_post_form_preserves_blank_values_and_replaces_invalid_utf8():
    form = read_bounded_post_form(
        io.BytesIO(b"name=alice&empty=&bad=%FF"),
        str(len(b"name=alice&empty=&bad=%FF")),
    )

    assert form["name"] == ["alice"]
    assert form["empty"] == [""]
    assert form["bad"] == ["\ufffd"]


def test_read_bounded_post_form_allows_exact_limit():
    payload = b"x=" + (b"a" * (MAX_WEB_POST_BODY_BYTES - 2))

    form = read_bounded_post_form(io.BytesIO(payload), str(len(payload)))

    assert form["x"] == ["a" * (MAX_WEB_POST_BODY_BYTES - 2)]


def test_read_bounded_post_form_rejects_over_limit():
    payload = b"x=" + (b"a" * MAX_WEB_POST_BODY_BYTES)

    with pytest.raises(WebError, match="bounded web input limit"):
        read_bounded_post_form(io.BytesIO(payload), str(len(payload)))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("localhost:8765", "localhost"),
        ("LOCALHOST.", "localhost"),
        ("127.0.0.1:8765", "127.0.0.1"),
        ("[::1]:8765", "::1"),
        ("bad host", ""),
        ("http://localhost", ""),
    ],
)
def test_normalized_request_host(value, expected):
    assert normalized_request_host(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("localhost:8765", 8765),
        ("127.0.0.1:12345", 12345),
        ("[::1]:6543", 6543),
        ("localhost", None),
        ("[::1]", None),
        ("bad:port", None),
        ("localhost:99999", None),
    ],
)
def test_explicit_request_host_port(value, expected):
    assert explicit_request_host_port(value) == expected


def test_forwarded_host_values_splits_proxy_header():
    assert forwarded_host_values("localhost:12345, 127.0.0.1:8765") == (
        "localhost:12345",
        "127.0.0.1:8765",
    )
    assert forwarded_host_values("  ") == ()


def test_forwarded_port_values_keeps_valid_ports():
    assert forwarded_port_values("12345, bad, 99999, 8765") == (12345, 8765)
    assert forwarded_port_values("  ") == ()


def test_forwarded_header_host_values_extracts_host_fields():
    assert forwarded_header_host_values('for=127.0.0.1;host="localhost:12345";proto=http') == (
        "localhost:12345",
    )
    assert forwarded_header_host_values("for=127.0.0.1;proto=http") == ()


def test_request_host_allowed_defaults_to_local_hosts():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))

    assert request_host_allowed("localhost:8765", settings) is True
    assert request_host_allowed("127.0.0.1:8765", settings) is True
    assert request_host_allowed("[::1]:8765", settings) is True
    assert request_host_allowed("external.example:8765", settings) is False


def test_request_host_allows_external_host_for_explicit_nonlocal_bind():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), allow_nonlocal_web_bind=True)

    assert request_host_allowed("external.example:8765", settings) is True


def test_render_web_audit_log_line_keeps_tokens_safe():
    event = WebAuditEvent(
        name="owner_raw_source_access",
        fields=(
            ("reason", "viewer_matches_query_user"),
            ("raw", "SELECT secret FROM table"),
        ),
    )

    line = render_web_audit_log_line(event, request_id="req-123")

    assert line.startswith("[Query Doctor audit] ")
    assert "event=owner_raw_source_access" in line
    assert "request_id=req-123" in line
    assert "reason=viewer_matches_query_user" in line
    assert "SELECT secret" not in line
    assert "raw=redacted" in line


def test_settings_for_request_headers_uses_configured_viewer_identity_header():
    settings = WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        viewer_identity_header="X-QD-Viewer",
    )

    resolved = settings_for_request_headers(settings, {"X-QD-Viewer": "analyst_one"})

    assert resolved is not settings
    assert resolved.viewer_identity.mode == VIEWER_IDENTITY_AUTHENTICATED
    assert resolved.viewer_identity.viewer_user == "analyst_one"
    assert resolved.viewer_identity.viewer_raw_subjects == ("analyst_one",)


def test_settings_for_request_headers_fails_closed_without_valid_viewer_header():
    settings = WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        viewer_identity_header="X-QD-Viewer",
    )

    missing = settings_for_request_headers(settings, {})
    service = settings_for_request_headers(
        settings,
        {"X-QD-Viewer": "impala/host.example.com@EXAMPLE.COM"},
    )

    assert missing.viewer_identity.mode == VIEWER_IDENTITY_UNAUTHENTICATED
    assert missing.viewer_identity.viewer_raw_subjects == ()
    assert service.viewer_identity.mode == VIEWER_IDENTITY_UNAUTHENTICATED
    assert service.viewer_identity.viewer_raw_subjects == ()


def test_settings_for_request_headers_fails_closed_for_duplicate_viewer_header_values():
    class MultiValueHeaders:
        def __init__(self, values):
            self.values = values

        def get_all(self, name):
            return self.values.get(name)

    settings = WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        viewer_identity_header="X-QD-Viewer",
    )

    single = settings_for_request_headers(
        settings,
        MultiValueHeaders({"X-QD-Viewer": ["analyst_one"]}),
    )
    duplicate = settings_for_request_headers(
        settings,
        MultiValueHeaders({"X-QD-Viewer": ["analyst_one", "other_user"]}),
    )

    assert single.viewer_identity.mode == VIEWER_IDENTITY_AUTHENTICATED
    assert single.viewer_identity.viewer_raw_subjects == ("analyst_one",)
    assert duplicate.viewer_identity.mode == VIEWER_IDENTITY_UNAUTHENTICATED
    assert duplicate.viewer_identity.viewer_raw_subjects == ()


def test_settings_for_request_headers_ignores_unconfigured_spoof_header():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))

    resolved = settings_for_request_headers(settings, {"X-QD-Viewer": "analyst_one"})

    assert resolved is settings
    assert resolved.viewer_identity.mode == VIEWER_IDENTITY_UNAUTHENTICATED


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("http://localhost:8765", True),
        ("http://127.0.0.1:8765", True),
        ("http://[::1]:8765", True),
        ("https://localhost:8765", True),
        ("http://localhost:9999", False),
        ("http://external.example:8765", False),
        ("null", False),
        ("http://user:" + "pass@localhost:8765", False),
        ("http://localhost:8765/path", False),
        ("http://localhost:8765?x=1", False),
    ],
)
def test_request_origin_allowed_defaults_to_same_local_origin(value, expected):
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert request_origin_allowed(value, settings) is expected


def test_request_origin_allows_local_forwarded_host_port():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "http://localhost:12345",
            settings,
            request_host_value="localhost:12345",
        )
        is True
    )
    assert (
        request_origin_allowed(
            "http://localhost:9999",
            settings,
            request_host_value="localhost:12345",
        )
        is False
    )


def test_request_origin_allows_local_x_forwarded_host_port():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "http://localhost:12345",
            settings,
            request_host_value="127.0.0.1:8765",
            forwarded_host_value="localhost:12345",
        )
        is True
    )
    assert (
        request_origin_allowed(
            "http://localhost:9999",
            settings,
            request_host_value="127.0.0.1:8765",
            forwarded_host_value="localhost:12345",
        )
        is False
    )


def test_request_origin_allows_local_x_forwarded_host_with_separate_port():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "http://localhost:12345",
            settings,
            request_host_value="127.0.0.1:8765",
            forwarded_host_value="localhost",
            forwarded_port_value="12345",
        )
        is True
    )


def test_request_origin_allows_local_standard_forwarded_host_port():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "http://localhost:12345",
            settings,
            request_host_value="127.0.0.1:8765",
            forwarded_header_value='for=127.0.0.1;host="localhost:12345";proto=http',
        )
        is True
    )


def test_request_origin_allows_null_origin_with_local_referer():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "null",
            settings,
            request_host_value="127.0.0.1:8765",
            referer_value="http://127.0.0.1:8765/",
        )
        is True
    )


def test_request_origin_rejects_null_origin_without_local_referer():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert request_origin_allowed("null", settings, request_host_value="127.0.0.1:8765") is False
    assert (
        request_origin_allowed(
            "null",
            settings,
            request_host_value="127.0.0.1:8765",
            referer_value="http://external.example:8765/",
        )
        is False
    )
    assert (
        request_origin_allowed(
            "null",
            settings,
            request_host_value="127.0.0.1:8765",
            referer_value="http://127.0.0.1:9999/",
        )
        is False
    )


def test_request_origin_ignores_nonlocal_x_forwarded_host_port():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "http://localhost:12345",
            settings,
            request_host_value="127.0.0.1:8765",
            forwarded_host_value="external.example:12345",
        )
        is False
    )


def test_request_origin_ignores_x_forwarded_port_without_local_forwarded_host():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)

    assert (
        request_origin_allowed(
            "http://localhost:12345",
            settings,
            request_host_value="127.0.0.1:8765",
            forwarded_port_value="12345",
        )
        is False
    )


def test_request_origin_allows_external_origin_for_explicit_nonlocal_bind():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), allow_nonlocal_web_bind=True)

    assert request_origin_allowed("http://external.example:8765", settings) is True


def test_new_request_id_is_hex_uuid():
    request_id = new_request_id()

    assert len(request_id) == 32
    assert set(request_id) <= set("0123456789abcdef")


def test_web_handler_rejects_untrusted_host_without_echoing_it():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    request.path = "/"
    request.headers = {"Host": "external.example:8765"}
    request.write_html = lambda status, body: captured.update({"status": status, "body": body})

    request.do_GET()

    assert captured["status"] == 400
    assert "outside the local web allowlist" in captured["body"]
    assert "external.example" not in captured["body"]


def test_web_handler_rejects_untrusted_post_origin_before_reading_body():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    class UnreadablePostBody(io.BytesIO):
        def read(self, *args, **kwargs):
            raise AssertionError(
                "untrusted Origin should be rejected before reading the request body"
            )

    request.path = "/analyze"
    request.headers = {"Host": "localhost:8765", "Origin": "http://external.example:8765"}
    request.rfile = UnreadablePostBody(b"query_id=abc%3Adef")
    request.write_html = lambda status, body: captured.update({"status": status, "body": body})

    request.do_POST()

    assert captured["status"] == 403
    assert "POST Origin outside the local web allowlist" in captured["body"]
    assert "external.example" not in captured["body"]


def test_web_handler_accepts_local_forwarded_origin():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)
    handler = make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)

    request.headers = {
        "Host": "127.0.0.1:8765",
        "Origin": "http://localhost:12345",
        "X-Forwarded-Host": "localhost:12345",
    }

    assert request.request_origin_is_allowed() is True


def test_web_handler_accepts_null_origin_with_local_referer():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), port=8765)
    handler = make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)

    request.headers = {
        "Host": "127.0.0.1:8765",
        "Origin": "null",
        "Referer": "http://127.0.0.1:8765/",
    }

    assert request.request_origin_is_allowed() is True


def test_web_handler_adds_security_headers_to_html_response():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(
        settings,
        analysis_func=lambda *args, **kwargs: None,
        request_id_factory=lambda: "req-001",
    )
    request = handler.__new__(handler)
    captured: dict[str, object] = {"headers": []}

    request.send_response = lambda status: captured.__setitem__("status", status)
    request.send_header = lambda name, value: captured["headers"].append((name, value))
    request.end_headers = lambda: None
    request.wfile = io.BytesIO()

    request.write_html(200, "<html></html>")

    headers = dict(captured["headers"])
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "same-origin"
    assert headers["X-Frame-Options"] == "DENY"
    assert (
        headers["Permissions-Policy"]
        == "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in headers["Content-Security-Policy"]
    assert headers["X-Request-ID"] == "req-001"
    assert headers["Cache-Control"] == "no-store"


def test_web_handler_assigns_distinct_request_ids_to_responses():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    request_ids = iter(["req-001", "req-002"])
    handler = make_handler(
        settings,
        analysis_func=lambda *args, **kwargs: None,
        request_id_factory=lambda: next(request_ids),
    )
    captured_headers: list[list[tuple[str, str]]] = []

    for _ in range(2):
        request = handler.__new__(handler)
        captured: dict[str, object] = {"headers": []}
        request.send_response = lambda status: captured.__setitem__("status", status)
        request.send_header = lambda name, value: captured["headers"].append((name, value))
        request.end_headers = lambda: None
        request.wfile = io.BytesIO()

        request.write_html(200, "<html></html>")
        captured_headers.append(captured["headers"])

    assert dict(captured_headers[0])["X-Request-ID"] == "req-001"
    assert dict(captured_headers[1])["X-Request-ID"] == "req-002"


def test_web_handler_adds_request_id_to_redirect_response():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(
        settings,
        analysis_func=lambda *args, **kwargs: None,
        request_id_factory=lambda: "req-redirect",
    )
    request = handler.__new__(handler)
    captured: dict[str, object] = {"headers": []}

    request.send_response = lambda status: captured.__setitem__("status", status)
    request.send_header = lambda name, value: captured["headers"].append((name, value))
    request.end_headers = lambda: None

    request.write_route_response(WebRouteResponse.redirect("/batch"))

    headers = dict(captured["headers"])
    assert captured["status"] == 303
    assert headers["Location"] == "/batch"
    assert headers["X-Request-ID"] == "req-redirect"


def test_web_handler_logs_request_id(capsys):
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(
        settings,
        analysis_func=lambda *args, **kwargs: None,
        request_id_factory=lambda: "req-log",
    )
    request = handler.__new__(handler)
    request.address_string = lambda: "127.0.0.1"

    request.log_message('"%s" %s', "GET /batch HTTP/1.1", 200)

    captured = capsys.readouterr()
    assert "request_id=req-log" in captured.err
    assert "GET /batch HTTP/1.1" in captured.err


def test_static_asset_route_serves_only_allowlisted_files():
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    store = WebJobStore()

    response = route_get_request("/static/app.css", settings, store)

    assert response is not None
    assert response.status == 200
    assert response.content_type == "text/css; charset=utf-8"
    assert "color-scheme:light" in response.body
    assert route_get_request("/static/../app.py", settings, store) is None
    assert route_get_request("/static/..%2fapp.py", settings, store) is None
    assert route_get_request("/static/./app.css", settings, store) is None
    assert route_get_request("/static/app.css/", settings, store) is None
    assert route_get_request("/static/missing.css", settings, store) is None


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/app.css", "text/css; charset=utf-8"),
        ("/static/app.js", "application/javascript; charset=utf-8"),
        ("/static/theme-bootstrap.js", "application/javascript; charset=utf-8"),
    ],
)
def test_static_asset_response_uses_security_headers(path, content_type):
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(
        settings,
        analysis_func=lambda *args, **kwargs: None,
        request_id_factory=lambda: "req-static",
    )
    request = handler.__new__(handler)
    captured: dict[str, object] = {"headers": []}

    request.path = path
    request.headers = {"Host": "localhost:8765"}
    request.send_response = lambda status: captured.__setitem__("status", status)
    request.send_header = lambda name, value: captured["headers"].append((name, value))
    request.end_headers = lambda: None
    request.wfile = io.BytesIO()

    request.do_GET()

    headers = dict(captured["headers"])
    assert captured["status"] == 200
    assert headers["Content-Type"] == content_type
    assert int(headers["Content-Length"]) == len(request.wfile.getvalue())
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Request-ID"] == "req-static"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert (
        headers["Permissions-Policy"]
        == "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    assert "'unsafe-inline'" not in headers["Content-Security-Policy"]


@pytest.mark.parametrize("content_length", ["not-an-int", "-1"])
def test_web_handler_rejects_invalid_post_content_length_before_reading_body(content_length):
    settings = WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    request.path = "/analyze"
    request.headers = {"Content-Length": content_length}
    request.rfile = UnreadableBody(b"")
    request.write_html = lambda status, body: captured.update({"status": status, "body": body})

    request.do_POST()

    assert captured["status"] == 400
    assert "Invalid POST content length" in captured["body"]
