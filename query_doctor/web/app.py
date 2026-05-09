"""HTTP handler factory for the local Query Doctor web UI."""

from __future__ import annotations

import subprocess
import sys
from http.server import BaseHTTPRequestHandler
from typing import BinaryIO, Callable
from urllib.parse import parse_qs

from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.query_analysis import run_query_id_analysis
from query_doctor.web.routes import WebRouteResponse, post_route_is_allowed, route_get_request, route_post_request
from query_doctor.web.subprocesses import Runner
from query_doctor.web.ui.pages import render_page


MAX_WEB_POST_BODY_BYTES = 320 * 1024
AnalysisFunc = Callable[[str, str, bool, WebSettings], object]
LOCAL_REQUEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    (
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'",
    ),
)


def parse_post_content_length(value: str | None) -> int:
    raw_value = value or "0"
    try:
        length = int(raw_value)
    except ValueError as exc:
        raise WebError("Invalid POST content length.") from exc
    if length < 0:
        raise WebError("Invalid POST content length.")
    return length


def read_bounded_post_form(
    body: BinaryIO,
    content_length_value: str | None,
    *,
    max_bytes: int = MAX_WEB_POST_BODY_BYTES,
) -> dict[str, list[str]]:
    length = parse_post_content_length(content_length_value)
    raw_body = body.read(min(length, max_bytes + 1))
    if length > max_bytes:
        raise WebError("Submitted form exceeds the bounded web input limit.")
    return parse_qs(raw_body.decode("utf-8", errors="replace"), keep_blank_values=True)


def normalized_request_host(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    host = value.strip()
    if any(char.isspace() for char in host) or "/" in host or "@" in host:
        return ""
    if host.startswith("["):
        closing = host.find("]")
        if closing == -1:
            return ""
        return host[1:closing].lower()
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.lower().rstrip(".")


def request_host_allowed(value: str | None, settings: WebSettings) -> bool:
    if settings.allow_nonlocal_web_bind:
        return True
    host = normalized_request_host(value)
    if host is None:
        return True
    allowed_hosts = set(LOCAL_REQUEST_HOSTS)
    bind_host = normalized_request_host(settings.host)
    if bind_host and bind_host not in {"0.0.0.0", "::"}:
        allowed_hosts.add(bind_host)
    return host in allowed_hosts


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_query_id_analysis,
    job_store: WebJobStore | None = None,
    runner: Runner = subprocess.run,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if not self.request_host_is_allowed():
                self.write_rejected_host_response()
                return
            response = route_get_request(self.path, settings, store)
            if response is not None:
                self.write_route_response(response)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if not self.request_host_is_allowed():
                self.write_rejected_host_response()
                return
            if not post_route_is_allowed(self.path):
                self.send_error(404)
                return
            try:
                form = read_bounded_post_form(self.rfile, self.headers.get("Content-Length"))
            except WebError as exc:
                status = 413 if "bounded web input limit" in str(exc) else 400
                self.write_html(status, render_page(settings, active_nav="batch", error=exc))
                return
            response = route_post_request(
                self.path,
                form,
                settings,
                store,
                analysis_func=analysis_func,
                runner=runner,
            )
            if response is not None:
                self.write_route_response(response)
                return
            self.send_error(404)

        def write_html(self, status: int, body: str) -> None:
            self.write_body(status, body, "text/html; charset=utf-8")

        def write_route_response(self, response: WebRouteResponse) -> None:
            if response.location is not None:
                self.send_response(response.status)
                self.send_header("Location", response.location)
                self.send_header("Cache-Control", "no-store")
                self.send_security_headers()
                self.end_headers()
                return
            if response.content_type.startswith("application/json"):
                self.write_json(response.status, response.body)
            elif response.content_type.startswith("text/html"):
                self.write_html(response.status, response.body)
            else:
                self.write_body(response.status, response.body, response.content_type)

        def write_body(self, status: int, body: str, content_type: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.send_security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def write_json(self, status: int, body: str) -> None:
            self.write_body(status, body, "application/json; charset=utf-8")

        def request_host_is_allowed(self) -> bool:
            headers = getattr(self, "headers", {})
            host_value = headers.get("Host") if hasattr(headers, "get") else None
            return request_host_allowed(host_value, settings)

        def write_rejected_host_response(self) -> None:
            error = WebError("Refusing request Host header outside the local web allowlist.")
            self.write_html(400, render_page(settings, active_nav="batch", error=error))

        def send_security_headers(self) -> None:
            if getattr(self, "_query_doctor_security_headers_sent", False):
                return
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            self._query_doctor_security_headers_sent = True

        def end_headers(self) -> None:
            self.send_security_headers()
            super().end_headers()

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[Query Doctor web] {self.address_string()} {fmt % args}", file=sys.stderr)

    return QueryDoctorWebHandler
