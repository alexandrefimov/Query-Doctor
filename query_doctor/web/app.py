"""HTTP handler factory for the local Query Doctor web UI."""

from __future__ import annotations

from dataclasses import replace
import subprocess
import sys
import uuid
from http.server import BaseHTTPRequestHandler
from typing import BinaryIO, Callable
from urllib.parse import parse_qs, urlsplit

from query_doctor.web.audit import WebAuditEvent, render_web_audit_log_line
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.query_analysis import run_query_id_analysis
from query_doctor.web.routes import (
    WebRouteResponse,
    post_route_is_allowed,
    route_get_request,
    route_post_request,
)
from query_doctor.web.subprocesses import Runner
from query_doctor.web.ui.pages import render_page
from query_doctor.web.viewer_identity import authenticated_viewer_identity_from_header_value


MAX_WEB_POST_BODY_BYTES = 320 * 1024
AnalysisFunc = Callable[[str, str, bool, WebSettings], object]
RequestIdFactory = Callable[[], str]
LOCAL_REQUEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
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


def new_request_id() -> str:
    return uuid.uuid4().hex


def parse_post_content_length(value: str | None) -> int:
    raw_value = value or "0"
    try:
        length = int(raw_value)
    except ValueError as exc:
        raise WebError(
            "Invalid POST content length.",
            title="Request body length is invalid",
            reason_code="web.post_content_length_invalid",
            stage="Reading web request",
            next_step="Retry the request from the Query Doctor web form.",
        ) from exc
    if length < 0:
        raise WebError(
            "Invalid POST content length.",
            title="Request body length is invalid",
            reason_code="web.post_content_length_invalid",
            stage="Reading web request",
            next_step="Retry the request from the Query Doctor web form.",
        )
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
        raise WebError(
            "Submitted form exceeds the bounded web input limit.",
            title="Submitted form is too large",
            reason_code="web.post_body_too_large",
            stage="Reading web request",
            next_step="Reduce the submitted form payload and retry.",
        )
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


def explicit_request_host_port(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    host = value.strip()
    port_value = ""
    if host.startswith("["):
        closing = host.find("]")
        if closing == -1:
            return None
        remainder = host[closing + 1 :]
        if not remainder.startswith(":"):
            return None
        port_value = remainder[1:]
    elif host.count(":") == 1:
        _, port_value = host.rsplit(":", 1)
    if not port_value or not port_value.isdigit():
        return None
    port = int(port_value)
    return port if 0 < port <= 65535 else None


def forwarded_host_values(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def forwarded_port_values(value: str | None) -> tuple[int, ...]:
    if value is None or not value.strip():
        return ()
    ports: list[int] = []
    for part in value.split(","):
        raw_port = part.strip()
        if not raw_port.isdigit():
            continue
        port = int(raw_port)
        if 0 < port <= 65535:
            ports.append(port)
    return tuple(ports)


def forwarded_header_host_values(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ()
    hosts: list[str] = []
    for element in value.split(","):
        for field in element.split(";"):
            key, separator, raw_field_value = field.strip().partition("=")
            if separator != "=" or key.strip().lower() != "host":
                continue
            field_value = raw_field_value.strip()
            if len(field_value) >= 2 and field_value[0] == field_value[-1] == '"':
                field_value = field_value[1:-1]
            if field_value:
                hosts.append(field_value)
    return tuple(hosts)


def local_web_allowed_ports(
    settings: WebSettings,
    *,
    request_host_value: str | None = None,
    forwarded_host_value: str | None = None,
    forwarded_port_value: str | None = None,
    forwarded_header_value: str | None = None,
) -> set[int]:
    allowed_ports = {settings.port}
    if not request_host_allowed(request_host_value, settings):
        return allowed_ports
    request_host_port = explicit_request_host_port(request_host_value)
    if request_host_port is not None:
        allowed_ports.add(request_host_port)
    forwarded_ports = forwarded_port_values(forwarded_port_value)
    for forwarded_host in (
        *forwarded_host_values(forwarded_host_value),
        *forwarded_header_host_values(forwarded_header_value),
    ):
        if not request_host_allowed(forwarded_host, settings):
            continue
        forwarded_port = explicit_request_host_port(forwarded_host)
        if forwarded_port is not None:
            allowed_ports.add(forwarded_port)
        else:
            allowed_ports.update(forwarded_ports)
    return allowed_ports


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


def request_origin_allowed(
    value: str | None,
    settings: WebSettings,
    *,
    request_host_value: str | None = None,
    forwarded_host_value: str | None = None,
    forwarded_port_value: str | None = None,
    forwarded_header_value: str | None = None,
    referer_value: str | None = None,
) -> bool:
    if value is None or not value.strip():
        return True
    if settings.allow_nonlocal_web_bind:
        return True
    origin = value.strip()
    allowed_ports = local_web_allowed_ports(
        settings,
        request_host_value=request_host_value,
        forwarded_host_value=forwarded_host_value,
        forwarded_port_value=forwarded_port_value,
        forwarded_header_value=forwarded_header_value,
    )
    if origin == "null":
        return request_url_allowed_for_local_web(
            referer_value, settings, allowed_ports=allowed_ports
        )
    if any(char.isspace() for char in origin):
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    try:
        origin_host = parsed.hostname
        origin_port = parsed.port
    except ValueError:
        return False
    if origin_port is not None and origin_port not in allowed_ports:
        return False
    return request_host_allowed(origin_host, settings)


def request_url_allowed_for_local_web(
    value: str | None, settings: WebSettings, *, allowed_ports: set[int]
) -> bool:
    if value is None or not value.strip():
        return False
    if any(char.isspace() for char in value):
        return False
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if port is not None and port not in allowed_ports:
        return False
    return request_host_allowed(host, settings)


def settings_for_request_headers(settings: WebSettings, headers: object) -> WebSettings:
    header_name = settings.viewer_identity_header
    if not header_name:
        return settings
    header_value = single_trusted_header_value(headers, header_name)
    viewer_identity = authenticated_viewer_identity_from_header_value(header_value)
    return replace(settings, viewer_identity=viewer_identity)


def single_trusted_header_value(headers: object, header_name: str) -> object | None:
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = get_all(header_name)
        if values is None:
            return None
        if isinstance(values, str):
            value_tuple = (values,)
        else:
            value_tuple = tuple(values)
        if len(value_tuple) != 1:
            return None
        return value_tuple[0]
    get = getattr(headers, "get", None)
    if callable(get):
        return get(header_name)
    return None


def _safe_header_value_for_log(value: str | None, *, max_chars: int = 180) -> str:
    if value is None:
        return "<missing>"
    safe = "".join(char if 32 <= ord(char) < 127 else "?" for char in value.strip())
    if len(safe) > max_chars:
        return safe[:max_chars] + "..."
    return safe or "<empty>"


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_query_id_analysis,
    job_store: WebJobStore | None = None,
    runner: Runner = subprocess.run,
    request_id_factory: RequestIdFactory = new_request_id,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.request_id()
            if not self.request_host_is_allowed():
                self.write_rejected_host_response()
                return
            request_settings = self.settings_for_request()
            response = route_get_request(self.path, request_settings, store)
            if response is not None:
                self.write_route_response(response)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            self.request_id()
            if not self.request_host_is_allowed():
                self.write_rejected_host_response()
                return
            if not self.request_origin_is_allowed():
                self.write_rejected_origin_response()
                return
            if not post_route_is_allowed(self.path):
                self.send_error(404)
                return
            try:
                form = read_bounded_post_form(self.rfile, self.headers.get("Content-Length"))
            except WebError as exc:
                status = 413 if exc.reason_code == "web.post_body_too_large" else 400
                self.write_html(
                    status,
                    render_page(self.settings_for_request(), active_nav="batch", error=exc),
                )
                return
            request_settings = self.settings_for_request()
            response = route_post_request(
                self.path,
                form,
                request_settings,
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
            self.write_audit_event(response.audit_event)
            if response.location is not None:
                self.send_response(response.status)
                self.send_header("Location", response.location)
                self.send_header("Cache-Control", "no-store")
                self.send_request_id_header()
                self.send_security_headers()
                self.end_headers()
                return
            if response.content_type.startswith("application/json"):
                self.write_json(response.status, response.body)
            elif response.content_type.startswith("text/html"):
                self.write_html(response.status, response.body)
            else:
                self.write_body(
                    response.status,
                    response.body,
                    response.content_type,
                    download_filename=response.download_filename,
                )

        def write_body(
            self,
            status: int,
            body: str,
            content_type: str,
            *,
            download_filename: str | None = None,
        ) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if download_filename is not None:
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{download_filename}"'
                )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.send_request_id_header()
            self.send_security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def write_json(self, status: int, body: str) -> None:
            self.write_body(status, body, "application/json; charset=utf-8")

        def write_audit_event(self, event: WebAuditEvent | None) -> None:
            if event is None:
                return
            print(
                render_web_audit_log_line(event, request_id=self.request_id()),
                file=sys.stderr,
            )

        def request_host_is_allowed(self) -> bool:
            headers = getattr(self, "headers", {})
            host_value = headers.get("Host") if hasattr(headers, "get") else None
            return request_host_allowed(host_value, settings)

        def request_origin_is_allowed(self) -> bool:
            headers = getattr(self, "headers", {})
            origin_value = headers.get("Origin") if hasattr(headers, "get") else None
            host_value = headers.get("Host") if hasattr(headers, "get") else None
            forwarded_host_value = (
                headers.get("X-Forwarded-Host") if hasattr(headers, "get") else None
            )
            forwarded_port_value = (
                headers.get("X-Forwarded-Port") if hasattr(headers, "get") else None
            )
            forwarded_header_value = headers.get("Forwarded") if hasattr(headers, "get") else None
            referer_value = headers.get("Referer") if hasattr(headers, "get") else None
            return request_origin_allowed(
                origin_value,
                settings,
                request_host_value=host_value,
                forwarded_host_value=forwarded_host_value,
                forwarded_port_value=forwarded_port_value,
                forwarded_header_value=forwarded_header_value,
                referer_value=referer_value,
            )

        def write_rejected_host_response(self) -> None:
            error = WebError(
                "Refusing request Host header outside the local web allowlist.",
                title="Request host is not allowed",
                reason_code="web.host_not_allowed",
                stage="Checking web request origin",
                next_step="Open Query Doctor through the configured local host and port.",
            )
            self.write_html(400, render_page(settings, active_nav="batch", error=error))

        def write_rejected_origin_response(self) -> None:
            error = WebError(
                "Refusing POST Origin outside the local web allowlist.",
                title="Request origin is not allowed",
                reason_code="web.origin_not_allowed",
                stage="Checking web request origin",
                next_step="Submit the form from the Query Doctor page served by this web session.",
            )
            headers = getattr(self, "headers", {})
            origin_value = headers.get("Origin") if hasattr(headers, "get") else None
            host_value = headers.get("Host") if hasattr(headers, "get") else None
            forwarded_host_value = (
                headers.get("X-Forwarded-Host") if hasattr(headers, "get") else None
            )
            forwarded_port_value = (
                headers.get("X-Forwarded-Port") if hasattr(headers, "get") else None
            )
            forwarded_header_value = headers.get("Forwarded") if hasattr(headers, "get") else None
            referer_value = headers.get("Referer") if hasattr(headers, "get") else None
            print(
                "[Query Doctor web] rejected POST Origin "
                f"request_id={self.request_id()} "
                f"host={_safe_header_value_for_log(host_value)} "
                f"origin={_safe_header_value_for_log(origin_value)} "
                f"referer={_safe_header_value_for_log(referer_value)} "
                f"x_forwarded_host={_safe_header_value_for_log(forwarded_host_value)} "
                f"x_forwarded_port={_safe_header_value_for_log(forwarded_port_value)} "
                f"forwarded={_safe_header_value_for_log(forwarded_header_value)}",
                file=sys.stderr,
            )
            self.write_html(403, render_page(settings, active_nav="batch", error=error))

        def settings_for_request(self) -> WebSettings:
            headers = getattr(self, "headers", {})
            return settings_for_request_headers(settings, headers)

        def request_id(self) -> str:
            current = getattr(self, "_query_doctor_request_id", None)
            if current is None:
                current = request_id_factory()
                self._query_doctor_request_id = current
            return current

        def send_request_id_header(self) -> None:
            if getattr(self, "_query_doctor_request_id_header_sent", False):
                return
            self.send_header("X-Request-ID", self.request_id())
            self._query_doctor_request_id_header_sent = True

        def send_security_headers(self) -> None:
            if getattr(self, "_query_doctor_security_headers_sent", False):
                return
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            self._query_doctor_security_headers_sent = True

        def end_headers(self) -> None:
            self.send_request_id_header()
            self.send_security_headers()
            super().end_headers()

        def log_message(self, fmt: str, *args: object) -> None:
            print(
                f"[Query Doctor web] {self.address_string()} request_id={self.request_id()} {fmt % args}",
                file=sys.stderr,
            )

    return QueryDoctorWebHandler
