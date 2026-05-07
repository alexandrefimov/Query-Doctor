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


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_query_id_analysis,
    job_store: WebJobStore | None = None,
    runner: Runner = subprocess.run,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            response = route_get_request(self.path, settings, store)
            if response is not None:
                self.write_route_response(response)
                return
            self.send_error(404)

        def do_POST(self) -> None:
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
                self.end_headers()
                return
            if response.content_type.startswith("application/json"):
                self.write_json(response.status, response.body)
            else:
                self.write_html(response.status, response.body)

        def write_body(self, status: int, body: str, content_type: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def write_json(self, status: int, body: str) -> None:
            self.write_body(status, body, "application/json; charset=utf-8")

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[Query Doctor web] {self.address_string()} {fmt % args}", file=sys.stderr)

    return QueryDoctorWebHandler
